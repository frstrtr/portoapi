#!/usr/bin/env bash
set -euo pipefail

# Stop previously running portoapi components to avoid duplicate instances

kill_by_pattern() {
  local pattern="$1"
  local pids
  # shellcheck disable=SC2009
  pids=$(ps aux | grep -E "$pattern" | grep -v grep | awk '{print $2}') || true
  if [ -n "$pids" ]; then
    echo "[stop] killing $pattern -> $pids"
    # Try graceful first, then force
    kill -TERM $pids 2>/dev/null || true
    sleep 0.5
    kill -KILL $pids 2>/dev/null || true
  fi
}

echo "[stop] scanning for running components"

# Uvicorn API server started by run_all.sh
kill_by_pattern "uvicorn .*src.api.v1.main:app"

# Telegram bot main process
kill_by_pattern "python .*src/bot/main_bot.py"

# Keeper bot
kill_by_pattern "python .*src/services/keeper_bot.py"

# Gas station status loop (inline Python in run_all)
kill_by_pattern "src/core/services/gas_station.py|gasstation status loop"

echo "[stop] done"
