#!/bin/bash

echo "🔍 Checking OT telemetry..."

docker ps --format "table {{.Names}}\t{{.Status}}"

docker exec -it redis redis-cli XLEN hil:telemetry
docker exec -it redis redis-cli XREVRANGE hil:telemetry + - COUNT 1

echo "✅ If XLEN > 0 → system is working"
