#!/usr/bin/env bash
# Opens an SSH local port-forward through the Zabbix-Agent-Server EC2 box so a
# local run of this agent can reach the Telrad BreezeVIEW CLI (port 9383 on
# 216.145.121.132), which firewalls by source IP to that EC2 box's address —
# see README.md's Telrad section and TELRAD_BREEZEVIEW_CLI_HOST/_PORT in .env.
#
# Run this in its own terminal/session before running the agent, or in the
# background with `./scripts/telrad-breezeview-cli-tunnel.sh &`. It stays open until killed.
#
# While this tunnel is up, point the agent at the forwarded local port instead
# of the real host, e.g. for a one-off local run:
#   TELRAD_BREEZEVIEW_CLI_HOST="localhost" python main.py --dry-run --controllers telrad
#
# Local-dev only — production runs on the EC2 box itself, which is already
# whitelisted and doesn't need this tunnel. Configured via TELRAD_BREEZEVIEW_CLI_TUNNEL_* in
# .env (see .env.example).
set -euo pipefail

cd "$(dirname "$0")/.."
set -a
source ./.env
set +a

: "${TELRAD_BREEZEVIEW_CLI_TUNNEL_SSH_KEY:?Set TELRAD_BREEZEVIEW_CLI_TUNNEL_SSH_KEY in .env}"
: "${TELRAD_BREEZEVIEW_CLI_TUNNEL_SSH_USER:?Set TELRAD_BREEZEVIEW_CLI_TUNNEL_SSH_USER in .env}"
: "${TELRAD_BREEZEVIEW_CLI_TUNNEL_SSH_HOST:?Set TELRAD_BREEZEVIEW_CLI_TUNNEL_SSH_HOST in .env}"
: "${TELRAD_BREEZEVIEW_CLI_TUNNEL_REMOTE:?Set TELRAD_BREEZEVIEW_CLI_TUNNEL_REMOTE in .env}"
: "${TELRAD_BREEZEVIEW_CLI_TUNNEL_LOCAL_PORT:?Set TELRAD_BREEZEVIEW_CLI_TUNNEL_LOCAL_PORT in .env}"

echo "[telrad-breezeview-cli-tunnel] starting: localhost:${TELRAD_BREEZEVIEW_CLI_TUNNEL_LOCAL_PORT} -> ${TELRAD_BREEZEVIEW_CLI_TUNNEL_REMOTE} via ${TELRAD_BREEZEVIEW_CLI_TUNNEL_SSH_USER}@${TELRAD_BREEZEVIEW_CLI_TUNNEL_SSH_HOST}"

ssh -i "$TELRAD_BREEZEVIEW_CLI_TUNNEL_SSH_KEY" -L "${TELRAD_BREEZEVIEW_CLI_TUNNEL_LOCAL_PORT}:${TELRAD_BREEZEVIEW_CLI_TUNNEL_REMOTE}" "${TELRAD_BREEZEVIEW_CLI_TUNNEL_SSH_USER}@${TELRAD_BREEZEVIEW_CLI_TUNNEL_SSH_HOST}" -N &
tunnel_pid=$!
cleanup() {
  echo "[telrad-breezeview-cli-tunnel] stopping (pid $tunnel_pid)"
  kill "$tunnel_pid" 2>/dev/null
}
trap cleanup EXIT
trap exit INT TERM

echo "[telrad-breezeview-cli-tunnel] started (pid $tunnel_pid)"
wait "$tunnel_pid"
