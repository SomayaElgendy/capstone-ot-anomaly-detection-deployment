#!/bin/bash

set -e

GHCR_OWNER="somayaelgendy"
REPO_NAME="capstone-ot-anomaly-detection-deployment"

echo "======================================"
echo " TAGGING IMAGES FOR GHCR"
echo "======================================"

docker tag capstone-django-backend:latest ghcr.io/$GHCR_OWNER/$REPO_NAME-django-backend:latest
docker tag capstone-stage12-producer:latest ghcr.io/$GHCR_OWNER/$REPO_NAME-stage12-producer:latest
docker tag capstone-stage3-service:latest ghcr.io/$GHCR_OWNER/$REPO_NAME-stage3-service:latest

echo ""
echo "======================================"
echo " PUSHING IMAGES TO GHCR"
echo "======================================"

docker push ghcr.io/$GHCR_OWNER/$REPO_NAME-django-backend:latest
docker push ghcr.io/$GHCR_OWNER/$REPO_NAME-stage12-producer:latest
docker push ghcr.io/$GHCR_OWNER/$REPO_NAME-stage3-service:latest

echo ""
echo "✅ Images pushed successfully."
