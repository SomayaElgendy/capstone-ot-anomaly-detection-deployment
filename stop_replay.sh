#!/bin/bash

set -e

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

echo "======================================"
echo " STOPPING ALERT REPLAY"
echo "======================================"

docker compose -f docker-compose.ghcr.yml stop stage12-producer || true
docker compose -f docker-compose.ghcr.yml rm -f stage12-producer || true

echo ""
echo "✅ Alert replay stopped."
echo "Other services are still running."
echo "======================================"
