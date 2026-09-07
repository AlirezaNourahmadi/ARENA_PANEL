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
: "${admin_password:?Set ARENA_ADMIN_PASSWORD or ARENA_ACCEPTANCE_PASSWORD}"
runtime_dir="${TMPDIR:-/tmp}/arena-acceptance-$$"
mkdir -p "$runtime_dir"

xray_pid() {
  docker compose exec -T arena sh -lc \
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
  jq -n --arg protocol "$protocol" --arg id "$id" --arg path "$path" '{
    log:{loglevel:"warning"},
    inbounds:[
      {listen:"0.0.0.0",port:18180,protocol:"socks",settings:{udp:true}},
      {listen:"0.0.0.0",port:18153,protocol:"dokodemo-door",settings:{address:"1.1.1.1",port:53,network:"tcp,udp"}}
    ],
    outbounds:[{
      protocol:$protocol,
      settings:{vnext:[{address:"caddy",port:80,users:[{id:$id,encryption:(if $protocol == "vless" then "none" else null end),alterId:(if $protocol == "vmess" then 0 else null end),security:(if $protocol == "vmess" then "auto" else null end)}]}]},
      streamSettings:{network:"ws",security:"none",wsSettings:{path:$path,host:"localhost"}}
    }]
  } | walk(if type == "object" then with_entries(select(.value != null)) else . end)' > "$output"
}

run_client() {
  local protocol="$1" config="$2" url="$3"
  local container="arena-acceptance-${protocol}-$$"
  docker run --rm -v "$config:/etc/xray/config.json:ro" \
    ghcr.io/xtls/xray-core:26.3.27 run -test -c /etc/xray/config.json >/dev/null
  docker run --rm -d --name "$container" --network arena_default \
    -v "$config:/etc/xray/config.json:ro" \
    ghcr.io/xtls/xray-core:26.3.27 run -c /etc/xray/config.json >/dev/null
  containers+=("$container")
  sleep 1
  docker run --rm --network arena_default curlimages/curl:8.16.0 \
    --max-time 15 --socks5-hostname "$container:18180" -sS -o /dev/null \
    -w '%{http_code}' "$url"
  docker stop "$container" >/dev/null
  containers=("${containers[@]/$container}")
}

make_client_config vless "$vless_id" "$vless_node" "$runtime_dir/vless-client.json"
make_client_config vmess "$vmess_id" "$vmess_node" "$runtime_dir/vmess-client.json"
google_code=$(run_client vless "$runtime_dir/vless-client.json" https://www.google.com/generate_204)
cloudflare_code=$(run_client vmess "$runtime_dir/vmess-client.json" https://cp.cloudflare.com/generate_204)

# DNS/UDP is checked separately through the VLESS data plane.
dns_container="arena-acceptance-dns-$$"
docker run --rm -d --name "$dns_container" --network arena_default \
  -v "$runtime_dir/vless-client.json:/etc/xray/config.json:ro" \
  ghcr.io/xtls/xray-core:26.3.27 run -c /etc/xray/config.json >/dev/null
containers+=("$dns_container")
sleep 1
dns_answer=$(docker run --rm --network arena_default alpine:3.22 sh -c \
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
echo "xray_pid=$xray_pid_after dynamic_user_sync=ok"
echo "user=$user_id vless_node=$vless_node vmess_node=$vmess_node"
echo "cleanup=ok"
echo "runtime=$runtime_dir"
