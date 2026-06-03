#!/bin/bash

set -e

echo "🚀 Starting OT Simulation..."

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "📁 OT directory: $SCRIPT_DIR"

OT_VENV="$HOME/capstone_ot_venv"

if [ ! -d "$OT_VENV" ]; then
    echo "🐍 Creating OT virtual environment in $OT_VENV..."
    python3 -m venv "$OT_VENV"
fi

echo "🐍 Activating OT venv..."
source "$OT_VENV/bin/activate"

echo "📦 Installing OT requirements..."
pip install -r requirements.txt

echo "⚙️ Regenerating simulation..."
python3 main.py config/water_bottle_factory

echo "🖥️ Syncing custom OT UI files..."
cp src/components/ui.py simulation/containers/ui/src/ui.py
cp src/components/app_lib.py simulation/containers/ui/src/app_lib.py
cp src/components/utils.py simulation/containers/ui/src/utils.py
cp src/components/ics_system.png simulation/containers/ui/src/ics_system.png

rm -rf simulation/containers/ui/src/pages
cp -r src/components/pages simulation/containers/ui/src/pages

echo "🛑 Stopping old OT containers..."
docker compose down --remove-orphans

echo "🌐 Fixing OT network..."
docker network rm ics_simlab 2>/dev/null || true

echo "🚀 Starting OT containers..."
docker compose up -d

echo "✅ OT Simulation running!"
echo "OT Dashboard: http://localhost:8501"
echo "👉 Run ./check_ot.sh to confirm telemetry"
