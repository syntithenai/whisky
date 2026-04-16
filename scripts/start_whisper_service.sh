#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOCKER_BIN="${DOCKER_BIN:-docker}"
SERVICE_PORT="${WHISPER_SERVICE_PORT:-10010}"
CONTAINER_NAME="${WHISPER_SERVICE_CONTAINER_NAME:-whisky-whisper-service}"
IMAGE_NAME="${WHISPER_SERVICE_IMAGE:-whisky-whisper-service:local}"
APP_DIR="${WHISKY_WHISPER_APP_DIR:-$ROOT_DIR/docker/whisper}"
MODEL_SOURCE_PATH="${WHISPER_SERVICE_MODEL_SOURCE:-/home/stever/projects/whisper models/ggml-large-v3.bin}"
MODEL_CACHE_DIR="${WHISPER_SERVICE_MODEL_DIR:-$ROOT_DIR/docker/whisper/models}"
MODEL_FILENAME="${WHISPER_SERVICE_MODEL_FILENAME:-$(basename "$MODEL_SOURCE_PATH")}"
BACKEND_PREFERENCE="${WHISPER_BACKEND_PREFERENCE:-auto}"
CPU_FALLBACK="${WHISPER_CPU_FALLBACK:-true}"
REBUILD_IMAGE="${WHISPER_SERVICE_REBUILD:-0}"
HEALTH_URL="${WHISPER_SERVICE_URL:-http://127.0.0.1:${SERVICE_PORT}}/health"

mkdir -p "$MODEL_CACHE_DIR"

MODEL_PATH="$MODEL_CACHE_DIR/$MODEL_FILENAME"
if [[ ! -f "$MODEL_PATH" ]]; then
    if [[ -f "$MODEL_SOURCE_PATH" ]]; then
        cp --reflink=auto "$MODEL_SOURCE_PATH" "$MODEL_PATH"
    else
        echo "Whisper model not found at $MODEL_SOURCE_PATH" >&2
        exit 1
    fi
fi

if ! command -v "$DOCKER_BIN" >/dev/null 2>&1; then
    echo "docker not found" >&2
    exit 1
fi

if "$DOCKER_BIN" ps --format '{{.Names}}' | grep -Fx "$CONTAINER_NAME" >/dev/null 2>&1; then
    if python3 - <<PY
import json
from urllib.request import urlopen

with urlopen("$HEALTH_URL", timeout=3) as resp:
    data = json.loads(resp.read().decode("utf-8", errors="replace"))
raise SystemExit(0 if data.get("status") == "healthy" else 1)
PY
    then
        echo "$CONTAINER_NAME already running"
        exit 0
    fi
fi

if "$DOCKER_BIN" ps -a --format '{{.Names}}' | grep -Fx "$CONTAINER_NAME" >/dev/null 2>&1; then
    "$DOCKER_BIN" rm -f "$CONTAINER_NAME" >/dev/null
fi

if [[ "$REBUILD_IMAGE" == "1" ]] || ! "$DOCKER_BIN" image inspect "$IMAGE_NAME" >/dev/null 2>&1; then
    "$DOCKER_BIN" build -t "$IMAGE_NAME" -f "$APP_DIR/Dockerfile" "$APP_DIR"
fi

DOCKER_ARGS=(
    run
    -d
    --restart
    unless-stopped
    --name
    "$CONTAINER_NAME"
    -p
    "127.0.0.1:${SERVICE_PORT}:10000"
    --device
    /dev/dri:/dev/dri
    -e
    "MODEL_PATH=/models/${MODEL_FILENAME}"
    -e
    "WHISPER_BACKEND_PREFERENCE=${BACKEND_PREFERENCE}"
    -e
    "WHISPER_CPU_FALLBACK=${CPU_FALLBACK}"
    -v
    "$MODEL_CACHE_DIR:/models:ro"
    "$IMAGE_NAME"
)

"$DOCKER_BIN" "${DOCKER_ARGS[@]}" >/dev/null

for _attempt in $(seq 1 60); do
    if python3 - <<PY
import json
from urllib.request import urlopen

with urlopen("$HEALTH_URL", timeout=3) as resp:
    data = json.loads(resp.read().decode("utf-8", errors="replace"))
raise SystemExit(0 if data.get("status") == "healthy" else 1)
PY
    then
        echo "$CONTAINER_NAME is healthy on $HEALTH_URL"
        exit 0
    fi
    sleep 1
done

echo "Timed out waiting for $CONTAINER_NAME to become healthy" >&2
"$DOCKER_BIN" logs "$CONTAINER_NAME" >&2 || true
exit 1