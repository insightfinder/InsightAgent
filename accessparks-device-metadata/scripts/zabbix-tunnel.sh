#!/usr/bin/env bash
# Opens the SSH port-forward to the AccessParks Zabbix server so the agent can
# reach it at http://localhost:9999/zabbix (ZABBIX_URL in .env). Also
# forwards the Positron controller through this SAME SSH connection when
# POSITRON_TUNNEL_REMOTE/POSITRON_TUNNEL_LOCAL_PORT are set in .env —
# Positron (192.168.102.16) lives on the same internal subnet as Zabbix
# (192.168.102.31), reachable via the same SSH jump host, so it rides this
# one tunnel instead of needing a second SSH process.
#
# Run this in its own terminal/session before running the agent, or in the
# background with `./scripts/zabbix-tunnel.sh &`. It stays open until killed.
#
# Requires sshpass (`apt-get install sshpass` on Debian/Ubuntu,
# `brew install hudochenkov/sshpass/sshpass` on macOS).
# Credentials are read from .env — never hardcode them here, this file is
# not gitignored.
set -euo pipefail

cd "$(dirname "$0")/.."
set -a
source ./.env
set +a

: "${ZABBIX_TUNNEL_SSH_HOST:?Set ZABBIX_TUNNEL_SSH_HOST in .env}"
: "${ZABBIX_TUNNEL_SSH_PORT:?Set ZABBIX_TUNNEL_SSH_PORT in .env}"
: "${ZABBIX_TUNNEL_SSH_USER:?Set ZABBIX_TUNNEL_SSH_USER in .env}"
: "${ZABBIX_TUNNEL_SSH_PASSWORD:?Set ZABBIX_TUNNEL_SSH_PASSWORD in .env}"
: "${ZABBIX_TUNNEL_REMOTE:?Set ZABBIX_TUNNEL_REMOTE in .env}"
: "${ZABBIX_TUNNEL_LOCAL_PORT:?Set ZABBIX_TUNNEL_LOCAL_PORT in .env}"

export SSHPASS="$ZABBIX_TUNNEL_SSH_PASSWORD"

forwards=("-L" "${ZABBIX_TUNNEL_LOCAL_PORT}:${ZABBIX_TUNNEL_REMOTE}")
echo "[zabbix-tunnel] starting: localhost:${ZABBIX_TUNNEL_LOCAL_PORT} -> ${ZABBIX_TUNNEL_REMOTE} via ${ZABBIX_TUNNEL_SSH_USER}@${ZABBIX_TUNNEL_SSH_HOST}:${ZABBIX_TUNNEL_SSH_PORT}"

if [[ -n "${POSITRON_TUNNEL_REMOTE:-}" && -n "${POSITRON_TUNNEL_LOCAL_PORT:-}" ]]; then
  forwards+=("-L" "${POSITRON_TUNNEL_LOCAL_PORT}:${POSITRON_TUNNEL_REMOTE}")
  echo "[zabbix-tunnel] also forwarding: localhost:${POSITRON_TUNNEL_LOCAL_PORT} -> ${POSITRON_TUNNEL_REMOTE} (Positron)"
fi

sshpass -e ssh \
  "${forwards[@]}" \
  "${ZABBIX_TUNNEL_SSH_USER}@${ZABBIX_TUNNEL_SSH_HOST}" \
  -p "${ZABBIX_TUNNEL_SSH_PORT}" -N &
tunnel_pid=$!
cleanup() {
  echo "[zabbix-tunnel] stopping (pid $tunnel_pid)"
  kill "$tunnel_pid" 2>/dev/null
}
trap cleanup EXIT
trap exit INT TERM

echo "[zabbix-tunnel] started (pid $tunnel_pid)"
wait "$tunnel_pid"
