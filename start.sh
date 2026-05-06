#!/bin/bash
set -e

echo "Starting Xvfb..."
Xvfb :99 -screen 0 1280x1024x24 &
sleep 2

echo "Starting Claude Mem worker..."
# Ensure memories dir exists
mkdir -p /app/.memories
export CLAUDE_MEM_DATA_DIR=/app/.memories
npx claude-mem start &
sleep 5

echo "Starting Google Chrome..."
google-chrome \
    --remote-debugging-address=0.0.0.0 \
    --remote-debugging-port=9223 \
    --user-data-dir=/app/.profiles \
    --no-sandbox \
    --disable-dev-shm-usage \
    --disable-gpu \
    --window-size=1280,1024 \
    about:blank
