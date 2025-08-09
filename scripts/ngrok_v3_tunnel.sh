#!/usr/bin/env bash
# Start ngrok v3 HTTP tunnel to local API and update .env with public URL.
# Requirements: Linux, bash, curl, tar, sed, python3
set -euo pipefail
cd "$(dirname "$0")/.."

BIN_DIR="bin"
NGROK_BIN="$BIN_DIR/ngrok"
LOG_FILE="ngrok.out"
PID_FILE="ngrok.pid"

mkdir -p "$BIN_DIR"

# 1) Ensure ngrok v3 installed locally
need_dl=1
if [ -x "$NGROK_BIN" ]; then
  if "$NGROK_BIN" version 2>/dev/null | grep -qE '^ngrok version 3\.'; then
    need_dl=0
  fi
fi
if [ "$need_dl" -eq 1 ]; then
  echo "Downloading ngrok v3..."
  rm -f "$NGROK_BIN" "$BIN_DIR/ngrok.tgz"
  URLS=(
    "https://ngrok-agent.s3.amazonaws.com/ngrok-v3-stable-linux-amd64.tgz"
    "https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-linux-amd64.tgz"
  )
  for U in "${URLS[@]}"; do
    echo "Trying $U"
    if curl -fsSL "$U" -o "$BIN_DIR/ngrok.tgz"; then
      if tar -xzf "$BIN_DIR/ngrok.tgz" -C "$BIN_DIR" ngrok 2>/dev/null || tar -xzf "$BIN_DIR/ngrok.tgz" -C "$BIN_DIR" 2>/dev/null; then
        chmod +x "$NGROK_BIN" || true
        break
      fi
    fi
  done
fi

if ! [ -x "$NGROK_BIN" ]; then
  echo "Failed to install ngrok v3" >&2
  exit 1
fi

"$NGROK_BIN" version || true

# 2) Read authtoken from .env
if ! grep -q '^NGROK_AUTHTOKEN=' .env; then
  echo "NGROK_AUTHTOKEN not found in .env" >&2
  exit 1
fi
NGROK_AUTHTOKEN="$(grep '^NGROK_AUTHTOKEN=' .env | head -n1 | cut -d= -f2-)"

# Optional reserved domain
NGROK_DOMAIN=""
if grep -q '^NGROK_DOMAIN=' .env; then
  NGROK_DOMAIN="$(grep '^NGROK_DOMAIN=' .env | head -n1 | cut -d= -f2-)"
fi

# 3) Configure authtoken
"$NGROK_BIN" config add-authtoken "$NGROK_AUTHTOKEN"

# 4) Restart tunnel
if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  kill "$(cat "$PID_FILE")" || true
  sleep 1
fi

# Start pointing to local api (port from .env or default 8000)
API_PORT=$(grep -E '^API_PORT=' .env | head -n1 | cut -d= -f2- || true)
API_PORT=${API_PORT:-8000}

# Add a request header to bypass ngrok browser interstitial warning
ARGS=(http "http://127.0.0.1:${API_PORT}" --log=stdout --request-header-add "ngrok-skip-browser-warning: true")
if [ -n "$NGROK_DOMAIN" ]; then
  ARGS+=(--domain "$NGROK_DOMAIN")
fi
"$NGROK_BIN" "${ARGS[@]}" > "$LOG_FILE" 2>&1 & echo $! > "$PID_FILE"

# 5) Get public https URL
PUB_URL=""
for i in $(seq 1 30); do
  sleep 0.5
  if curl -fsS http://127.0.0.1:4040/api/tunnels >/dev/null 2>&1; then
    PUB_URL="$(
  curl -fsS http://127.0.0.1:4040/api/tunnels | /usr/bin/env python3 -c "import sys,json; j=json.load(sys.stdin); print(next((t.get('public_url') for t in j.get('tunnels',[]) if t.get('proto')=='https'), ''), end='')"
)"
  fi
  if [ -n "$PUB_URL" ]; then break; fi
  if [ -f "$LOG_FILE" ]; then
    PUB_URL=$(grep -oE "https://[a-zA-Z0-9.-]+\\.ngrok[-a-zA-Z0-9]*\\.app|https://[a-zA-Z0-9.-]+\\.ngrok\\.io" "$LOG_FILE" | head -n1 || true)
    if [ -n "$PUB_URL" ]; then break; fi
  fi
done

# If a reserved domain is configured, prefer it
if [ -z "$PUB_URL" ] && [ -n "$NGROK_DOMAIN" ]; then
  PUB_URL="https://${NGROK_DOMAIN}"
fi

if [ -z "$PUB_URL" ]; then
  echo "Could not determine ngrok public URL" >&2
  tail -n 100 "$LOG_FILE" >&2 || true
  exit 1
fi

echo "Public URL: $PUB_URL"

# 6) Update .env values
cp .env .env.bak.$(date +%s)
sed -i "s#^API_BASE_URL=.*#API_BASE_URL=${PUB_URL}/api/v1#g" .env || true
sed -i "s#^SETUP_URL_BASE=.*#SETUP_URL_BASE=${PUB_URL}#g" .env || true

grep -E '^(API_BASE_URL|SETUP_URL_BASE)=' .env

echo "Done. Restart your API and bot to apply the new URLs."
