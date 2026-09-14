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
docker_network="${ARENA_ACCEPTANCE_DOCKER_NETWORK:-arena_default}"
stats_wait="${ARENA_XRAY_STATS_INTERVAL_SECONDS:-15}"
reality_address="${ARENA_ACCEPTANCE_REALITY_ADDRESS:-}"
reality_port="${ARENA_ACCEPTANCE_REALITY_PORT:-}"
runtime_dir="${TMPDIR:-/tmp}/arena-reality-acceptance-$$"
mkdir -p "$runtime_dir"

if [[ -z "$admin_password" ]]; then
  echo "Acceptance credentials are not configured." >&2
  exit 1
fi

client_container="arena-reality-acceptance-$$"
payload_container="arena-reality-payload-$$"
user_id=""
cleanup() {
  docker stop "$client_container" "$payload_container" >/dev/null 2>&1 || true
  docker container rm "$client_container" "$payload_container" >/dev/null 2>&1 || true
  if [[ -n "$user_id" && -f "$runtime_dir/cookies.txt" ]]; then
    csrf=$(awk '$6 == "arena_csrf" {print $7}' "$runtime_dir/cookies.txt")
    curl -fsS -X DELETE -b "$runtime_dir/cookies.txt" -H "X-CSRF-Token: $csrf" \
      "$base_url/api/users/$user_id" >/dev/null 2>&1 || true
  fi
  rm -rf "$runtime_dir"
}
trap cleanup EXIT

jq -n --arg username "$admin_user" --arg password "$admin_password" \
  '{username:$username,password:$password}' > "$runtime_dir/login-request.json"
curl -fsS -c "$runtime_dir/cookies.txt" -H 'Content-Type: application/json' \
  -d @"$runtime_dir/login-request.json" "$base_url/api/auth/login" \
  > "$runtime_dir/login.json"
csrf=$(awk '$6 == "arena_csrf" {print $7}' "$runtime_dir/cookies.txt")

curl -fsS -b "$runtime_dir/cookies.txt" -H "X-CSRF-Token: $csrf" \
  "$base_url/api/nodes" > "$runtime_dir/nodes.json"
reality_node=$(jq -er \
  'first(.[] | select(.enabled == true and .protocol == "vless" and .transport == "tcp" and .security == "reality")) | .id' \
  "$runtime_dir/nodes.json")

jq -n --arg node "$reality_node" \
  '{name:"ARENA Reality Acceptance",quota_gb:1,validity_days:7,max_ips:1,speed_mbps:0,node_ids:[$node]}' \
  > "$runtime_dir/create-user.json"
curl -fsS -b "$runtime_dir/cookies.txt" -H "X-CSRF-Token: $csrf" \
  -H 'Content-Type: application/json' -d @"$runtime_dir/create-user.json" \
  "$base_url/api/users" > "$runtime_dir/user.json"
user_id=$(jq -r '.id' "$runtime_dir/user.json")

curl -fsS -b "$runtime_dir/cookies.txt" -H "X-CSRF-Token: $csrf" \
  "$base_url/api/users/$user_id/formats" > "$runtime_dir/formats.json"
reality_link=$(jq -er \
  '.direct_links[] | select(startswith("vless://") and contains("security=reality"))' \
  "$runtime_dir/formats.json")

REALITY_LINK="$reality_link" REALITY_ADDRESS="$reality_address" REALITY_PORT="$reality_port" \
  python3 - "$runtime_dir/client.json" <<'PY'
import json
import os
import sys
from urllib.parse import parse_qs, unquote, urlsplit

uri = urlsplit(os.environ["REALITY_LINK"])
query = parse_qs(uri.query)
config = {
    "log": {"loglevel": "warning"},
    "inbounds": [
        {"listen": "0.0.0.0", "port": 18190, "protocol": "socks", "settings": {"udp": True}}
    ],
    "outbounds": [
        {
            "tag": "proxy",
            "protocol": "vless",
            "settings": {
                "vnext": [
                    {
                        "address": os.environ.get("REALITY_ADDRESS") or uri.hostname,
                        "port": int(os.environ.get("REALITY_PORT") or uri.port),
                        "users": [
                            {
                                "id": unquote(uri.username or ""),
                                "encryption": "none",
                                "flow": query["flow"][0],
                            }
                        ],
                    }
                ]
            },
            "streamSettings": {
                "network": "tcp",
                "security": "reality",
                "realitySettings": {
                    "serverName": query["sni"][0],
                    "fingerprint": query.get("fp", ["chrome"])[0],
                    "password": query["pbk"][0],
                    "shortId": query["sid"][0],
                    "spiderX": query.get("spx", ["/"])[0],
                },
            },
        }
    ],
}
with open(sys.argv[1], "w", encoding="utf-8") as output:
    json.dump(config, output)
PY

docker run --rm -v "$runtime_dir/client.json:/etc/xray/config.json:ro" \
  ghcr.io/xtls/xray-core:26.3.27 run -test -c /etc/xray/config.json >/dev/null
docker run --rm -d --name "$client_container" --network "$docker_network" \
  -v "$runtime_dir/client.json:/etc/xray/config.json:ro" \
  ghcr.io/xtls/xray-core:26.3.27 run -c /etc/xray/config.json >/dev/null
expected_payload_bytes=$((20 * 1024 * 1024))
docker run --rm -d --name "$payload_container" --network "$docker_network" caddy:2.10-alpine \
  sh -c 'mkdir -p /www && dd if=/dev/zero of=/www/payload.bin bs=1M count=20 >/dev/null 2>&1 && caddy file-server --root /www --listen :18080' \
  >/dev/null
sleep 1

google_code=$(docker run --rm --network "$docker_network" curlimages/curl:8.16.0 \
  --max-time 15 --socks5-hostname "$client_container:18190" -sS -o /dev/null \
  -w '%{http_code}' https://www.google.com/generate_204)
payload_metrics=$(docker run --rm --network "$docker_network" curlimages/curl:8.16.0 \
  --max-time 40 --limit-rate 1m --socks5-hostname "$client_container:18190" -sS -o /dev/null \
  -w '%{size_download} %{speed_download} %{time_total}' \
  "http://$payload_container:18080/payload.bin")
read -r downloaded_bytes payload_speed payload_seconds <<< "$payload_metrics"

sleep "$((stats_wait + 3))"
curl -fsS -b "$runtime_dir/cookies.txt" -H "X-CSRF-Token: $csrf" \
  "$base_url/api/users/$user_id" > "$runtime_dir/accounted-user.json"
used_bytes=$(jq -r '.used_bytes' "$runtime_dir/accounted-user.json")
starts_at=$(jq -r '.starts_at' "$runtime_dir/accounted-user.json")
curl -fsS -b "$runtime_dir/cookies.txt" -H "X-CSRF-Token: $csrf" \
  "$base_url/api/logs?limit=50&user_id=$user_id" > "$runtime_dir/logs.json"
session_count=$(jq --arg user_id "$user_id" \
  '[.sessions[] | select(.user_id == $user_id and .user_agent == "Xray REALITY")] | length' \
  "$runtime_dir/logs.json")

if [[ "$google_code" != "204" || "$downloaded_bytes" != "$expected_payload_bytes" ]]; then
  echo "REALITY acceptance failed: data plane did not return expected payloads" >&2
  exit 1
fi
if [[ "$used_bytes" -le 0 || "$starts_at" == "null" || "$session_count" -le 0 ]]; then
  echo "REALITY acceptance failed: accounting or session trace was not persisted" >&2
  exit 1
fi

echo "google=$google_code payload=$downloaded_bytes/$expected_payload_bytes"
echo "speed_Bps=$payload_speed seconds=$payload_seconds"
echo "accounted_bytes=$used_bytes traced_sessions=$session_count"
echo "reality=ok cleanup=pending"
