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
mkdir -p data

# Functions to run components
start_api() {
  echo "[api] starting FastAPI on :8000"
  uvicorn src.api.v1.main:app --host 0.0.0.0 --port 8000 --reload
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
  echo "[gasstation] starting CLI (status loop)"
  python - <<'PY'
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from src.core.config import config
from src.core.services.gasstation.gas_station_service import GasStationService

gs = GasStationService(config.tron)
while True:
    try:
        st = gs.get_status()
        print("[gasstation]", st['network'], st['address'], f"bal={st['balance']:.2f}")
    except Exception as e:
        print("[gasstation][error]", e)
    time.sleep(60)
PY
}

# Supervisor: run components concurrently with logs
run_all() {
  echo "[run] launching components"
  # Create logs directory
  mkdir -p logs

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

  # Trap and cleanup
  trap 'echo "[run] stopping"; kill $API_PID $KEEPER_PID $BOT_PID $GAS_PID 2>/dev/null || true; wait' INT TERM
  echo "[run] PIDs: api=$API_PID keeper=$KEEPER_PID bot=$BOT_PID gas=$GAS_PID"
  wait
}

# Help
usage() {
  cat <<EOF
Usage: $0 <command>
Commands:
  all          Run API + Keeper + Bot + GasStation status loop (default)
  api          Run FastAPI server only
  bot          Run Telegram bot only
  keeper       Run keeper bot only
  gasstation   Run gas station status loop (debug)
EOF
}

cmd=${1:-all}
case "$cmd" in
  all) run_all ;;
  api) start_api ;;
  bot) start_bot ;;
  keeper) start_keeper ;;
  gasstation) start_gasstation_cli ;;
  *) usage ;;

esac
