#!/usr/bin/env bash
# KAIROS one-line launcher: installs anything missing, then runs the backend.
# Usage (from repo root):  ./kairos.sh
# Checks only (no run):    ./kairos.sh --check-only
set -euo pipefail
cd "$(dirname "$0")"
ROOT="$PWD"
CHECK_ONLY="${1:-}"

info() { echo "-- $*"; }
warn() { echo "WARN: $*" >&2; }
fail() { echo "FAIL: $*" >&2; exit 1; }

# 1) Python venv + deps -------------------------------------------------------
if [ ! -x "$ROOT/.venv/bin/python" ]; then
  info "creating .venv ..."
  python3 -m venv "$ROOT/.venv" || fail "need python3-venv (sudo apt install python3-venv)"
fi
if ! "$ROOT/.venv/bin/python" -c "import flask, torch, shap, sklearn" 2>/dev/null; then
  info "installing python deps (torch CPU, Flask, shap, sklearn — a few minutes) ..."
  "$ROOT/.venv/bin/pip" install -r "$ROOT/python-ml/requirements.txt" || fail "pip install failed"
fi
"$ROOT/.venv/bin/python" -c "import flask, torch, shap, sklearn; print('py-deps ok')" || fail "python deps still missing"

# 2) CMake (venv copy is enough; system cmake optional) ------------------------
if [ ! -x "$ROOT/.venv/bin/cmake" ]; then
  info "installing cmake into .venv ..."
  "$ROOT/.venv/bin/pip" install cmake || fail "cmake install failed"
fi

# 3) Java 21 -------------------------------------------------------------------
if ! java -version 2>&1 | grep -q "21\."; then
  if [ -d /usr/lib/jvm/java-21-openjdk-amd64 ]; then
    export JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64
    info "using $JAVA_HOME"
  elif command -v apt-get >/dev/null && sudo -n true 2>/dev/null; then
    info "installing openjdk-21 ..."
    sudo apt-get update -qq && sudo apt-get install -y -qq openjdk-21-jdk
    export JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64
  else
    fail "JDK 21 missing (sudo apt install openjdk-21-jdk)"
  fi
else
  export JAVA_HOME="${JAVA_HOME:-/usr/lib/jvm/java-21-openjdk-amd64}"
fi
[ -f "$ROOT/java-engine/mvnw" ] || fail "java-engine/mvnw missing"

# 4) Node/npm (24.21.0 per .node-version; build tolerates 22+) ------------------
if ! command -v node >/dev/null || ! command -v npm >/dev/null; then
  fail "node/npm missing (install Node 24: https://nodejs.org or sudo apt install nodejs npm)"
fi
if [ "$(cat "$ROOT/.node-version" 2>/dev/null || echo)" != "$(node --version 2>/dev/null | tr -d v)" ]; then
  warn "node $(node --version) differs from .node-version $(cat "$ROOT/.node-version" 2>/dev/null); continuing"
fi
if [ ! -d "$ROOT/react-ui/node_modules" ]; then
  info "npm ci (react-ui) ..."
  (cd "$ROOT/react-ui" && npm ci) || fail "npm ci failed"
fi

# 5) dumpcap (optional: static forecasts work without it) -----------------------
if ! command -v dumpcap >/dev/null && [ ! -x /usr/bin/dumpcap ]; then
  warn "dumpcap missing — live capture disabled (static forecasts still work)"
  warn "to enable: sudo apt install wireshark-common"
elif [ -x /usr/bin/dumpcap ] && ! /usr/bin/dumpcap -D >/dev/null 2>&1; then
  warn "dumpcap not executable by you — live capture disabled until fixed"
  warn "fix: sudo usermod -aG wireshark \$USER (then log back in)  OR  sudo chmod o+x /usr/bin/dumpcap"
fi

# 6) .env + weights -------------------------------------------------------------
[ -f "$ROOT/.env" ] || { cp "$ROOT/.env.example" "$ROOT/.env"; info "created .env from .env.example (offline default)"; }
[ -f "$ROOT/python-ml/weights/world_model_v1.pt" ] || warn "weights/world_model_v1.pt missing — /predict will fail"

# 7) Build native extractor and live helper ----------------------------------------------------------
info "building libkairos_native.so + kairos_live_stream ..."
"$ROOT/.venv/bin/cmake" -S "$ROOT/cpp-engine" -B "$ROOT/cpp-engine/build" -DBUILD_TESTING=ON >/dev/null
"$ROOT/.venv/bin/cmake" --build "$ROOT/cpp-engine/build" --target kairos_native kairos_live_stream -j2 >/dev/null
[ -f "$ROOT/cpp-engine/build/libkairos_native.so" ] || fail "native extractor build failed"
[ -x "$ROOT/cpp-engine/build/kairos_live_stream" ] || fail "live helper build failed"

if [ "$CHECK_ONLY" = "--check-only" ]; then
  echo "OK: everything installed — run ./kairos.sh to start the backend"
  exit 0
fi

# 8) Run ------------------------------------------------------------------------
info "starting backend (ML :5000 + Java :8080, Ctrl+C to stop) ..."
exec "$ROOT/scripts/start_backend.sh"
