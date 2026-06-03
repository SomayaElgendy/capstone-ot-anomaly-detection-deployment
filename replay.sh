#!/bin/bash

set -e

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

echo "======================================"
echo " REPLAYING STAGE 1/2 ALERTS"
echo "======================================"

echo "[1/2] Making sure AI services are running..."
docker compose -f docker-compose.ghcr.yml up -d --no-build redis django-web django-consumer stage3

echo ""
echo "[2/2] Restarting alert producer..."
docker compose -f docker-compose.ghcr.yml up --force-recreate -d stage12-producer

echo ""
echo "✅ Replay started."
echo "Watch consumer logs with:"
echo "docker compose -f docker-compose.ghcr.yml logs -f django-consumer"
echo ""
echo "Dashboard:"
echo "http://localhost:8000/dashboard/"
echo "======================================"
