#!/usr/bin/env bash
set -euo pipefail

if [[ -f .env ]]; then
  set -a
  source .env
  set +a
fi

base_url="${ARENA_ACCEPTANCE_URL:-http://localhost:8080}"
admin_user="${ARENA_ACCEPTANCE_USER:-${ARENA_ADMIN_USERNAME:-admin}}"
admin_password="${ARENA_ACCEPTANCE_PASSWORD:-${ARENA_ADMIN_PASSWORD:-}}"
compose_file="${ARENA_ACCEPTANCE_COMPOSE_FILE:-docker-compose.yml}"
docker_network="${ARENA_ACCEPTANCE_DOCKER_NETWORK:-arena_default}"
proxy_address="${ARENA_ACCEPTANCE_PROXY_ADDRESS:-caddy}"
proxy_port="${ARENA_ACCEPTANCE_PROXY_PORT:-80}"
proxy_security="${ARENA_ACCEPTANCE_PROXY_SECURITY:-none}"
proxy_ws_host="${ARENA_ACCEPTANCE_WS_HOST:-localhost}"
proxy_server_name="${ARENA_ACCEPTANCE_SERVER_NAME:-$proxy_ws_host}"
if [[ -z "$admin_password" ]]; then
  echo "Acceptance credentials are not configured." >&2
  exit 1
fi
if [[ "$proxy_security" != "none" && "$proxy_security" != "tls" ]]; then
  echo "ARENA_ACCEPTANCE_PROXY_SECURITY must be none or tls." >&2
  exit 1
fi
runtime_dir="${TMPDIR:-/tmp}/arena-acceptance-$$"
mkdir -p "$runtime_dir"

xray_pid() {
  docker compose -f "$compose_file" exec -T arena sh -lc \
    'for path in /proc/[0-9]*; do read -r name < "$path/comm" || continue; [ "$name" = xray ] && basename "$path"; done; exit 0'
}

curl -fsS "$base_url/api/health" > "$runtime_dir/health.json"
xray_pid_before=$(xray_pid)
curl -fsS -c "$runtime_dir/cookies.txt" \
  -H 'Content-Type: application/json' \
  -d "{\"username\":\"$admin_user\",\"password\":\"$admin_password\"}" \
  "$base_url/api/auth/login" > "$runtime_dir/login.json"
csrf=$(awk '$6 == "arena_csrf" {print $7}' "$runtime_dir/cookies.txt")

curl -fsS -b "$runtime_dir/cookies.txt" -H "X-CSRF-Token: $csrf" \
  "$base_url/api/nodes" > "$runtime_dir/nodes.json"
vless_node=$(jq -r '.[] | select(.protocol == "vless") | .id' "$runtime_dir/nodes.json")
vmess_node=$(jq -r '.[] | select(.protocol == "vmess") | .id' "$runtime_dir/nodes.json")
jq -n --arg vless "$vless_node" --arg vmess "$vmess_node" \
  '{name:"ARENA Acceptance", quota_gb:1, validity_days:7, max_ips:1, speed_mbps:0, node_ids:[$vless,$vmess]}' \
  > "$runtime_dir/create.json"
curl -fsS -b "$runtime_dir/cookies.txt" -H "X-CSRF-Token: $csrf" \
  -H 'Content-Type: application/json' -d @"$runtime_dir/create.json" \
  "$base_url/api/users" > "$runtime_dir/user.json"
user_id=$(jq -r '.id' "$runtime_dir/user.json")
xray_pid_after=$(xray_pid)
if [[ -z "$xray_pid_before" || "$xray_pid_before" != "$xray_pid_after" ]]; then
  echo "acceptance failed: Xray restarted while adding a user" >&2
  exit 1
fi

curl -fsS -b "$runtime_dir/cookies.txt" -H "X-CSRF-Token: $csrf" \
  "$base_url/api/users/$user_id/formats" > "$runtime_dir/formats.json"
vless_link=$(jq -r '.direct_links[] | select(startswith("vless://"))' "$runtime_dir/formats.json")
vless_id=$(printf '%s' "$vless_link" | sed -E 's#vless://([^@]+)@.*#\1#')
vmess_link=$(jq -r '.direct_links[] | select(startswith("vmess://"))' "$runtime_dir/formats.json")
vmess_id=$(VMESS_LINK="$vmess_link" python3 -c 'import base64,json,os; raw=os.environ["VMESS_LINK"].split("://",1)[1]; raw += "=" * (-len(raw) % 4); print(json.loads(base64.urlsafe_b64decode(raw))["id"])')

containers=()
user_deleted=0
cleanup() {
  for container in "${containers[@]:-}"; do
    if [[ -n "$container" ]]; then
      docker stop "$container" >/dev/null 2>&1 || true
    fi
  done
  if [[ "$user_deleted" != "1" ]]; then
    curl -fsS -X DELETE -b "$runtime_dir/cookies.txt" -H "X-CSRF-Token: $csrf" \
      "$base_url/api/users/$user_id" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

make_client_config() {
  local protocol="$1" id="$2" node="$3" output="$4"
  local path="/edge/$node/$user_id"
  jq -n --arg protocol "$protocol" --arg id "$id" --arg path "$path" \
    --arg address "$proxy_address" --argjson port "$proxy_port" \
    --arg transport_security "$proxy_security" --arg ws_host "$proxy_ws_host" \
    --arg server_name "$proxy_server_name" '{
    log:{loglevel:"warning"},
    inbounds:[
      {listen:"0.0.0.0",port:18180,protocol:"socks",settings:{udp:true}},
      {listen:"0.0.0.0",port:18153,protocol:"dokodemo-door",settings:{address:"1.1.1.1",port:53,network:"tcp,udp"}}
    ],
    outbounds:[{
      protocol:$protocol,
      settings:{vnext:[{address:$address,port:$port,users:[{id:$id,encryption:(if $protocol == "vless" then "none" else null end),alterId:(if $protocol == "vmess" then 0 else null end),security:(if $protocol == "vmess" then "auto" else null end)}]}]},
      streamSettings:({network:"ws",security:$transport_security,wsSettings:{path:$path,host:$ws_host}} +
        (if $transport_security == "tls" then {tlsSettings:{serverName:$server_name,allowInsecure:false,alpn:["http/1.1"]}} else {} end))
    }]
  } | walk(if type == "object" then with_entries(select(.value != null)) else . end)' > "$output"
}

run_client() {
  local protocol="$1" config="$2" url="$3"
  local payload_url="${4:-}" expected_payload_bytes="${5:-}"
  local container="arena-acceptance-${protocol}-$$"
  docker run --rm -v "$config:/etc/xray/config.json:ro" \
    ghcr.io/xtls/xray-core:26.3.27 run -test -c /etc/xray/config.json >/dev/null
  docker run --rm -d --name "$container" --network "$docker_network" \
    -v "$config:/etc/xray/config.json:ro" \
    ghcr.io/xtls/xray-core:26.3.27 run -c /etc/xray/config.json >/dev/null
  containers+=("$container")
  sleep 1
  client_status_code=$(docker run --rm --network "$docker_network" curlimages/curl:8.16.0 \
    --max-time 15 --socks5-hostname "$container:18180" -sS -o /dev/null \
    -w '%{http_code}' "$url") || {
      docker stop "$container" >/dev/null 2>&1 || true
      return 1
    }
  client_payload_bytes="0"
  client_payload_speed="0"
  client_payload_seconds="0"
  if [[ -n "$payload_url" ]]; then
    local payload_metrics
    payload_metrics=$(docker run --rm --network "$docker_network" curlimages/curl:8.16.0 \
      --max-time 30 --socks5-hostname "$container:18180" -sS -o /dev/null \
      -w '%{size_download} %{speed_download} %{time_total}' "$payload_url") || {
        docker stop "$container" >/dev/null 2>&1 || true
        return 1
      }
    read -r client_payload_bytes client_payload_speed client_payload_seconds <<< "$payload_metrics"
    if [[ "$client_payload_bytes" != "$expected_payload_bytes" ]]; then
      echo "acceptance failed: received $client_payload_bytes of $expected_payload_bytes payload bytes" >&2
      docker stop "$container" >/dev/null 2>&1 || true
      return 1
    fi
  fi
  docker stop "$container" >/dev/null
  containers=("${containers[@]/$container}")
}

make_client_config vless "$vless_id" "$vless_node" "$runtime_dir/vless-client.json"
make_client_config vmess "$vmess_id" "$vmess_node" "$runtime_dir/vmess-client.json"
payload_container="arena-acceptance-payload-$$"
payload_bytes=$((8 * 1024 * 1024))
docker run --rm -d --name "$payload_container" --network "$docker_network" caddy:2.10-alpine \
  sh -c 'mkdir -p /www && dd if=/dev/zero of=/www/payload.bin bs=1M count=8 >/dev/null 2>&1 && caddy file-server --root /www --listen :18080' \
  >/dev/null
containers+=("$payload_container")
sleep 1

run_client vless "$runtime_dir/vless-client.json" \
  https://www.google.com/generate_204 "http://$payload_container:18080/payload.bin" "$payload_bytes"
google_code="$client_status_code"
payload_downloaded="$client_payload_bytes"
payload_speed="$client_payload_speed"
payload_seconds="$client_payload_seconds"
run_client vmess "$runtime_dir/vmess-client.json" https://cp.cloudflare.com/generate_204
cloudflare_code="$client_status_code"

# DNS/UDP is checked separately through the VLESS data plane.
dns_container="arena-acceptance-dns-$$"
docker run --rm -d --name "$dns_container" --network "$docker_network" \
  -v "$runtime_dir/vless-client.json:/etc/xray/config.json:ro" \
  ghcr.io/xtls/xray-core:26.3.27 run -c /etc/xray/config.json >/dev/null
containers+=("$dns_container")
sleep 1
dns_answer=$(docker run --rm --network "$docker_network" alpine:3.22 sh -c \
  "apk add --no-cache bind-tools >/dev/null && dig @$dns_container -p 18153 google.com A +short +time=5 +tries=1 | head -1")
docker stop "$dns_container" >/dev/null
containers=("${containers[@]/$dns_container}")

if [[ "$google_code" != "204" || "$cloudflare_code" != "204" || -z "$dns_answer" ]]; then
  echo "acceptance failed" >&2
  exit 1
fi

curl -fsS -X DELETE -b "$runtime_dir/cookies.txt" -H "X-CSRF-Token: $csrf" \
  "$base_url/api/users/$user_id" >/dev/null
user_deleted=1
xray_pid_final=$(xray_pid)
if [[ "$xray_pid_after" != "$xray_pid_final" ]]; then
  echo "acceptance failed: Xray restarted while removing a user" >&2
  exit 1
fi

echo "health=$(jq -r '.status' "$runtime_dir/health.json")"
echo "google=$google_code cloudflare=$cloudflare_code dns=$dns_answer"
echo "payload=$payload_downloaded/$payload_bytes speed_Bps=$payload_speed seconds=$payload_seconds"
echo "xray_pid=$xray_pid_after dynamic_user_sync=ok"
echo "user=$user_id vless_node=$vless_node vmess_node=$vmess_node"
echo "cleanup=ok"
echo "runtime=$runtime_dir"
