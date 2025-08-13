#!/usr/bin/env bash
set -euo pipefail

# Root of project
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")"/.. && pwd)"
cd "$ROOT_DIR"

# Ensure PYTHONPATH includes project root for imports like 'src.*'
export PYTHONPATH="$ROOT_DIR:${PYTHONPATH:-}"

# Load env
if [ -f .env ]; then
  # shellcheck disable=SC1091
  source .env
fi

# Ensure venv
if [ -d .venv ]; then
  source .venv/bin/activate
else
  echo "[setup] Creating virtualenv .venv"
  python3 -m venv .venv
  source .venv/bin/activate
  pip install -U pip
  if [ -f src/requirements.txt ]; then
    pip install -r src/requirements.txt
  fi
fi

# Ensure data dir
mkdir -p data logs

# Resolve API port (defaults to 8000)
API_PORT="${API_PORT:-8000}"

# Functions to run components
start_api() {
  echo "[api] starting FastAPI on :$API_PORT"
  uvicorn src.api.v1.main:app --host 0.0.0.0 --port "$API_PORT" --reload
}

start_bot() {
  echo "[bot] starting Telegram bot"
  python -u src/bot/main_bot.py
}

start_keeper() {
  echo "[keeper] starting keeper bot"
  python -u src/services/keeper_bot.py
}

start_gasstation_cli() {
  echo "[gasstation] starting status loop"
  python -u - <<'PY'
import time, signal, sys, logging
from src.core.services.gas_station import gas_station

# Reduce noisy shutdown logs
logging.getLogger("urllib3").setLevel(logging.WARNING)

stop = False

def _stop(*_):
    global stop
    stop = True

signal.signal(signal.SIGINT, _stop)
signal.signal(signal.SIGTERM, _stop)

try:
    while not stop:
        try:
            health = gas_station.check_connection_health()
            try:
                addr = gas_station.get_gas_wallet_address()
            except Exception:
                addr = 'N/A'
            print(f"[gasstation] node={health.get('node_type')} ok={health.get('connected')} block={health.get('latest_block')} lat={health.get('latency_ms')}ms addr={addr}", flush=True)
        except Exception as e:
            # Keep quiet on shutdown
            if stop:
                break
            print("[gasstation][error]", e, flush=True)
        # Sleep in small steps to react fast to signals
        for _ in range(30):
            if stop:
                break
            time.sleep(1)
except KeyboardInterrupt:
    pass
PY
}

start_ngrok() {
  echo "[ngrok] starting/refreshing tunnel to :$API_PORT"
  # Ensure API_PORT in .env for the script to pick up
  if grep -q '^API_PORT=' .env; then
    sed -i "s#^API_PORT=.*#API_PORT=${API_PORT}#g" .env
  else
    echo "API_PORT=${API_PORT}" >> .env
  fi
  bash scripts/ngrok_v3_tunnel.sh || true
  if [ -f ngrok.pid ]; then
    NGROK_PID=$(cat ngrok.pid)
    echo "[ngrok] pid=$NGROK_PID"
  fi
  if [ -f .env ]; then
    echo "[ngrok] URLs in .env:" && grep -E '^(API_BASE_URL|SETUP_URL_BASE)=' .env || true
  fi
}

# Supervisor: run components concurrently with logs
run_all() {
  local WANT_NGROK="${1:-auto}" # auto|force|off
  echo "[run] launching components"

  # Preflight: warn if another bot instance appears to be running (prevents TelegramConflictError)
  if ps aux | grep -E "python .*src/bot/main_bot.py" | grep -v grep >/dev/null; then
    echo "[warn] Another Telegram bot instance seems to be running. This can cause 'terminated by other getUpdates request'."
    echo "[hint] Run: scripts/stop_all.sh to terminate previous processes, then re-run this script."
  fi

  # Start API
  start_api 2>&1 | tee logs/api.log &
  API_PID=$!

  # Start keeper
  start_keeper 2>&1 | tee logs/keeper.log &
  KEEPER_PID=$!

  # Start bot
  start_bot 2>&1 | tee logs/bot.log &
  BOT_PID=$!

  # Start gasstation status loop
  start_gasstation_cli 2>&1 | tee logs/gasstation.log &
  GAS_PID=$!

  # Start ngrok if requested
  NGROK_PID=""
  if [ "$WANT_NGROK" = "force" ] || { [ "$WANT_NGROK" = "auto" ] && { [ -n "${NGROK_AUTHTOKEN:-}" ] || grep -q '^NGROK_AUTHTOKEN=' .env 2>/dev/null; }; }; then
    # Delay slightly to let API initialize
    sleep 1
    start_ngrok
  else
    echo "[ngrok] skipped (no token or disabled)"
  fi

  cleanup() {
    echo "[run] stopping"
    for pid in $API_PID $KEEPER_PID $BOT_PID $GAS_PID ${NGROK_PID:-}; do
      kill -TERM "$pid" 2>/dev/null || true
    done
    sleep 1
    for pid in $API_PID $KEEPER_PID $BOT_PID $GAS_PID ${NGROK_PID:-}; do
      kill -KILL "$pid" 2>/dev/null || true
    done
    wait
  }
  trap cleanup INT TERM

  echo "[run] PIDs: api=$API_PID keeper=$KEEPER_PID bot=$BOT_PID gas=$GAS_PID ngrok=${NGROK_PID:-none}"
  wait
}

# Help
usage() {
  cat <<EOF
Usage: $0 <command>
Commands:
  all            Run API + Keeper + Bot + GasStation loop; auto-start ngrok if token present (default)
  all-ngrok      Same as 'all' but force start ngrok tunnel
  api            Run FastAPI server only
  bot            Run Telegram bot only
  keeper         Run keeper bot only
  gasstation     Run gas station status loop (debug)
  ngrok          Run ngrok tunnel setup/update only
EOF
}

cmd=${1:-all}
case "$cmd" in
  all) run_all auto ;;
  all-ngrok) run_all force ;;
  api) start_api ;;
  bot) start_bot ;;
  keeper) start_keeper ;;
  gasstation) start_gasstation_cli ;;
  ngrok) start_ngrok ;;
  *) usage ;;

esac
