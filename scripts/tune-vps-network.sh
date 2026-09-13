#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo "Run this script as root." >&2
  exit 1
fi

root_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
install -m 0644 "$root_dir/deploy/arena-bbr.conf" /etc/modules-load.d/arena-bbr.conf
install -m 0644 "$root_dir/deploy/99-arena-network.conf" /etc/sysctl.d/99-arena-network.conf

modprobe tcp_bbr
sysctl --system >/dev/null
sysctl net.ipv4.tcp_congestion_control \
  net.ipv4.tcp_available_congestion_control \
  net.core.default_qdisc
