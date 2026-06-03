#!/bin/bash

set -e

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "======================================"
echo " CAPSTONE DEPLOYMENT STARTING"
echo "======================================"

echo "[1/3] Checking required files..."
cd "$ROOT_DIR"

if [ ! -f ".env" ]; then
    echo "ERROR: .env file not found."
    echo "Create .env and add: GROQ_API_KEY=your_key_here"
    exit 1
fi

if [ ! -f "docker-compose.ghcr.yml" ]; then
    echo "ERROR: docker-compose.ghcr.yml not found."
    exit 1
fi

if [ ! -f "ot/curtin-ics-simlab/run_ot.sh" ]; then
    echo "ERROR: OT run script not found."
    exit 1
fi

echo "Required files found."

echo ""
echo "[2/3] Starting OT simulator..."
cd "$ROOT_DIR/ot/curtin-ics-simlab"
chmod +x ./run_ot.sh
./run_ot.sh

echo ""
echo "[3/3] Starting AI/Django/Stage3 services without rebuilding..."
cd "$ROOT_DIR"
docker compose -f docker-compose.ghcr.yml up -d

echo ""
echo "Waiting a few seconds for services to initialize..."
sleep 5

echo ""
echo "Running service checks..."
echo "- Stage 3 health:"
curl -s http://localhost:8001/health || true
echo ""

echo ""
echo "Running containers:"
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep -E "capstone|redis|ui|plc|hmi|sensor|bottle|tank|network|conveyor" || true

echo ""
echo "======================================"
echo " DEPLOYMENT STARTED SUCCESSFULLY"
echo "======================================"
echo "OT Dashboard:      http://localhost:8501"
echo "Django Dashboard:  http://localhost:8000"
echo "Stage 3 Health:    http://localhost:8001/health"
echo ""
echo "Useful commands:"
echo "docker compose -f docker-compose.ghcr.yml logs -f"
echo "./stop_all.sh"
echo "======================================"
