#!/usr/bin/env bash
# KAIROS backend launcher — starts both backend services with one command:
#   1) python-ml Flask  (POST /predict, default 127.0.0.1:5000)
#   2) java-engine API (POST /forecast, default 127.0.0.1:8080)
#
# Usage:
#   ./scripts/start_backend.sh
#   KAIROS_ML_PORT=5001 SERVER_PORT=8081 ./scripts/start_backend.sh
# Stop: Ctrl+C (both services are killed automatically).
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$PWD"

# Load local .env if present (OFFLINE default: ONLINE_MODE=false, no key).
if [ -f "$ROOT/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  . "$ROOT/.env"
  set +a
fi

ML_HOST="${KAIROS_ML_HOST:-127.0.0.1}"
ML_PORT="${KAIROS_ML_PORT:-5000}"
JAVA_PORT="${SERVER_PORT:-8080}"
export KAIROS_ML_HOST="$ML_HOST" KAIROS_ML_PORT="$ML_PORT"
export KAIROS_ML_URL="${KAIROS_ML_URL:-http://${ML_HOST}:${ML_PORT}}"
export ONLINE_MODE="${ONLINE_MODE:-false}"

PYTHON="$ROOT/.venv/bin/python"
CMAKE="$ROOT/.venv/bin/cmake"
LIVE_HELPER="$ROOT/cpp-engine/build/kairos_live_stream"
LOG_DIR="${LOG_DIR:-/tmp}"
ML_LOG="$LOG_DIR/kairos-ml.log"
JAVA_LOG="$LOG_DIR/kairos-java.log"

# Preflight checks.
[ -x "$PYTHON" ] || { echo "FAIL: $PYTHON not found. Run: python3 -m venv .venv && .venv/bin/pip install -r python-ml/requirements.txt"; exit 1; }
[ -f "$ROOT/java-engine/mvnw" ] || { echo "FAIL: java-engine/mvnw not found"; exit 1; }
[ -f "$ROOT/python-ml/weights/world_model_v1.pt" ] || { echo "WARN: python-ml/weights/world_model_v1.pt missing — /predict will fail to load"; }
[ -x "$CMAKE" ] || { echo "FAIL: $CMAKE not found. Install requirements into .venv"; exit 1; }

echo "-- building bounded live-capture helper --"
"$CMAKE" -S "$ROOT/cpp-engine" -B "$ROOT/cpp-engine/build" -DBUILD_TESTING=ON >/dev/null
"$CMAKE" --build "$ROOT/cpp-engine/build" --target kairos_live_stream -j2 >/dev/null
[ -x "$LIVE_HELPER" ] || { echo "FAIL: live helper build did not produce $LIVE_HELPER"; exit 1; }
export KAIROS_LIVE_HELPER="${KAIROS_LIVE_HELPER:-$LIVE_HELPER}"
if [ ! -x /usr/bin/dumpcap ]; then
  echo "WARN: /usr/bin/dumpcap unavailable — static forecasts work, live capture is disabled"
fi
if [ -z "${KAIROS_LIVE_ALLOWED_INTERFACES:-}" ]; then
  echo "WARN: live interface allowlist is empty; set KAIROS_LIVE_ALLOWED_INTERFACES to opt in"
fi

wait_for_url() { # $1=url $2=name $3=timeout_s
  local url="$1" name="$2" timeout="${3:-90}" i=0
  echo "-- waiting for $name at $url (max ${timeout}s) --"
  until curl -sf -o /dev/null "$url" 2>/dev/null; do
    i=$((i+1))
    if [ "$i" -ge "$timeout" ]; then
      echo "FAIL: $name did not come up. See logs:"; echo "  $ML_LOG"; echo "  $JAVA_LOG"; exit 1
    fi
    sleep 1
  done
  echo "OK: $name is up"
}

wait_for_port() { # $1=port $2=name $3=timeout_s
  local port="$1" name="$2" timeout="${3:-120}" i=0
  echo "-- waiting for $name on port $port (max ${timeout}s) --"
  until curl -s -o /dev/null "http://127.0.0.1:${port}/" 2>/dev/null || \
        (command -v nc >/dev/null && nc -z 127.0.0.1 "$port" 2>/dev/null); do
    i=$((i+1))
    if [ "$i" -ge "$timeout" ]; then
      echo "FAIL: $name did not open port $port. See: $JAVA_LOG"; exit 1
    fi
    sleep 2
  done
  echo "OK: $name port $port is open"
}

ML_PID=""
JAVA_PID=""
TAIL_PID=""
cleanup() {
  echo; echo "-- stopping backend (ML + Java) --"
  for pid in "$TAIL_PID" "$JAVA_PID" "$ML_PID"; do
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
    fi
  done
}
trap cleanup INT TERM EXIT

echo "== KAIROS backend =="
echo "ML:   http://${ML_HOST}:${ML_PORT} (/predict)  log: $ML_LOG"
echo "Java: http://127.0.0.1:${JAVA_PORT} (/forecast)  log: $JAVA_LOG  ONLINE_MODE=$ONLINE_MODE"

echo "-- 1/2 starting python-ml --"
"$PYTHON" python-ml/app.py >"$ML_LOG" 2>&1 &
ML_PID=$!
wait_for_url "http://${ML_HOST}:${ML_PORT}/health" "python-ml" 90

echo "-- 2/2 starting java-engine --"
(cd "$ROOT/java-engine" && exec ./mvnw -q spring-boot:run -Dspring-boot.run.jvmArguments="-Dserver.port=${JAVA_PORT}") >"$JAVA_LOG" 2>&1 &
JAVA_PID=$!
wait_for_port "$JAVA_PORT" "java-engine" 180

echo
echo "== BOTH UP =="
echo "ML   health: curl http://${ML_HOST}:${ML_PORT}/health"
echo "Flow: React/UI -> POST http://127.0.0.1:${JAVA_PORT}/forecast/upload (file + rolloutSteps)"
echo "Logs: tail -f $ML_LOG $JAVA_LOG"
echo "Stop: Ctrl+C"
echo

# Keep running until Ctrl+C; show combined logs.
tail -n +1 -F "$ML_LOG" "$JAVA_LOG" &
TAIL_PID=$!
wait "$TAIL_PID"
