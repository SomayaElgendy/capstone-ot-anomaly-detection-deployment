#!/bin/bash

set -e

echo "======================================"
echo " PULLING CAPSTONE DOCKER IMAGES"
echo "======================================"

docker compose -f docker-compose.ghcr.yml pull

echo ""
echo "✅ Images pulled successfully."
