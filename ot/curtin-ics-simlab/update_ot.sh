#!/bin/bash

echo "🔄 Updating OT Simulation..."

cd ~/ICS-SimLab/capstone-ot-anomaly-detection/OT-simulator/ICS-SimLab/curtin-ics-simlab || exit

echo "🧹 Cleaning repo..."
git reset --hard
git clean -fd

echo "⬇️ Pulling latest changes..."
git pull

echo "🐍 Activating venv..."
source .venv/bin/activate

echo "⚙️ Regenerating simulation..."
python3 main.py config/water_bottle_factory

echo "🛑 Stopping old containers..."
docker compose down -v --remove-orphans

echo "🌐 Removing old network (if exists)..."
docker network rm ics_simlab 2>/dev/null || true

echo "🏗️ Rebuilding containers..."
docker compose build --no-cache

echo "🚀 Starting environment..."
docker compose up -d

echo "✅ Update complete!"
echo "👉 Run ./check_ot.sh to verify"
