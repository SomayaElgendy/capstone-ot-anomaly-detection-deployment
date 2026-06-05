#!/bin/bash

set -e

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
OT_DIR="$ROOT_DIR/ot/curtin-ics-simlab"
DB_PATH="$ROOT_DIR/backend/backend/db.sqlite3"
DJANGO_IMAGE="ghcr.io/somayaelgendy/capstone-ot-anomaly-detection-deployment-django-backend:latest"

echo "======================================"
echo " CAPSTONE DEPLOYMENT STARTING"
echo "======================================"

echo "[1/6] Checking required files..."

if [ ! -f "$ROOT_DIR/.env" ]; then
    echo "ERROR: .env file not found."
    echo "Create it using:"
    echo "cp .env.example .env"
    echo "Then add your GROQ_API_KEY."
    exit 1
fi

if [ ! -f "$ROOT_DIR/docker-compose.ghcr.yml" ]; then
    echo "ERROR: docker-compose.ghcr.yml not found."
    exit 1
fi

if [ ! -f "$OT_DIR/run_ot.sh" ]; then
    echo "ERROR: OT run script not found at:"
    echo "$OT_DIR/run_ot.sh"
    exit 1
fi

echo "Required files found."

echo ""
echo "[2/6] Checking Docker availability..."

if ! command -v docker >/dev/null 2>&1; then
    echo "ERROR: docker command not found."
    echo "Make sure Docker Desktop is installed and WSL integration is enabled."
    exit 1
fi

if ! docker ps >/dev/null 2>&1; then
    echo "ERROR: Docker is not accessible from Ubuntu."
    echo "Open Docker Desktop > Settings > Resources > WSL integration"
    echo "Enable Ubuntu-24.04, then restart Docker Desktop."
    exit 1
fi

echo "Docker is available."

echo ""
echo "[3/6] Installing required Ubuntu packages if missing..."

MISSING_PACKAGES=""

if ! command -v socat >/dev/null 2>&1; then
    MISSING_PACKAGES="$MISSING_PACKAGES socat"
fi

if ! command -v git >/dev/null 2>&1; then
    MISSING_PACKAGES="$MISSING_PACKAGES git"
fi

if ! command -v curl >/dev/null 2>&1; then
    MISSING_PACKAGES="$MISSING_PACKAGES curl"
fi

if ! command -v python3 >/dev/null 2>&1; then
    MISSING_PACKAGES="$MISSING_PACKAGES python3"
fi

if ! python3 -m venv --help >/dev/null 2>&1; then
    MISSING_PACKAGES="$MISSING_PACKAGES python3-venv"
fi

if ! command -v pip3 >/dev/null 2>&1; then
    MISSING_PACKAGES="$MISSING_PACKAGES python3-pip"
fi

if [ -n "$MISSING_PACKAGES" ]; then
    echo "Installing missing packages:$MISSING_PACKAGES"
    sudo apt update
    sudo apt install -y $MISSING_PACKAGES
else
    echo "Required Ubuntu packages are already installed."
fi

echo ""
echo "[4/6] Preparing shared SQLite database..."

mkdir -p "$ROOT_DIR/backend/backend"

# If db.sqlite3 exists as a directory, remove it.
if [ -d "$DB_PATH" ]; then
    echo "db.sqlite3 exists as a directory. Fixing it..."
    rm -rf "$DB_PATH"
fi

# If db.sqlite3 file is missing, copy the ready DB from the Django image.
if [ ! -f "$DB_PATH" ]; then
    echo "db.sqlite3 file is missing. Creating it from Django image..."

    docker pull "$DJANGO_IMAGE"

    docker rm -f temp-django-db >/dev/null 2>&1 || true
    docker create --name temp-django-db "$DJANGO_IMAGE" >/dev/null
    docker cp temp-django-db:/app/backend/db.sqlite3 "$DB_PATH"
    docker rm temp-django-db >/dev/null
fi

if [ ! -f "$DB_PATH" ]; then
    echo "ERROR: Failed to prepare db.sqlite3."
    exit 1
fi

echo "SQLite database ready:"
ls -lh "$DB_PATH"

echo ""
echo "[5/6] Preparing Stage 3 output folder..."

mkdir -p "$ROOT_DIR/stage3/outputs"

echo "Stage 3 outputs folder ready."

echo ""
echo "[6/6] Starting OT simulator..."

cd "$OT_DIR"
chmod +x ./run_ot.sh
./run_ot.sh

echo ""
echo "Starting AI/Django/Stage3 services..."
cd "$ROOT_DIR"
docker compose -f docker-compose.ghcr.yml up -d
echo ""
echo "Running Django database migrations..."
docker exec capstone-django-web python manage.py migrate --noinput

echo ""
echo "Waiting for services to initialize..."
sleep 5

echo ""
echo "Stage 3 health:"
curl -s http://localhost:8001/health || true
echo ""

echo ""
echo "Running project containers:"
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep -E "capstone|redis|ui|plc|hmi|sensor|bottle|tank|network|conveyor" || true

echo ""
echo "======================================"
echo " DEPLOYMENT STARTED"
echo "======================================"
echo "OT Dashboard:      http://localhost:8501"
echo "Django Dashboard:  http://localhost:8000"
echo "Stage 3 Health:    http://localhost:8001/health"
echo "======================================"
