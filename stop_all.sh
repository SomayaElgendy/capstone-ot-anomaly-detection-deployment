#!/bin/bash

set -e

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "======================================"
echo " STOPPING CAPSTONE DEPLOYMENT"
echo "======================================"

echo "[1/3] Stopping AI/Django/Stage3 compose services..."
cd "$ROOT_DIR"
docker compose -f docker-compose.ghcr.yml down --remove-orphans || true

echo ""
echo "[2/3] Stopping OT simulator compose services..."
cd "$ROOT_DIR/ot/curtin-ics-simlab"
docker compose down --remove-orphans || true

echo ""
echo "[3/3] Removing old manual/test containers if they exist..."
docker rm -f \
  capstone-redis \
  capstone-redis-test \
  capstone-stage3-test \
  capstone-django-test \
  capstone-django-ui-test \
  capstone-django-consumer-test \
  capstone-stage12-test \
  capstone-stage12-test-2 \
  capstone-stage3 \
  capstone-django-web \
  capstone-django-consumer \
  capstone-stage12-producer \
  capstone-ai-redis 2>/dev/null || true

echo ""
echo "Checking remaining running project containers..."
RUNNING_PROJECT_CONTAINERS=$(docker ps --format "{{.Names}}" | grep -E "capstone|redis|ui|plc|hmi|sensor|bottle|tank|network|conveyor" || true)

if [ -z "$RUNNING_PROJECT_CONTAINERS" ]; then
    echo "✅ No running capstone/OT project containers found."
else
    echo "⚠️ Some project containers are still running:"
    docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep -E "capstone|redis|ui|plc|hmi|sensor|bottle|tank|network|conveyor" || true
fi

echo ""
echo "======================================"
echo " ALL CAPSTONE SERVICES STOPPED"
echo "======================================"
