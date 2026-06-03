# Capstone OT Anomaly Detection Deployment Guide

This repository contains the deployment package for the capstone OT anomaly detection system.

The system includes:

1. OT simulator and OT dashboard
2. Django security monitoring dashboard
3. Redis alert pipeline
4. Stage 1/2 alert replay producer
5. Stage 3 IR/RAG incident response service

---

## 1. System Overview

The system has two main sides.

### A. OT Simulator Side

The OT simulator runs from the source files included in:

``bash
ot/curtin-ics-simlab/

It starts multiple OT containers, including:

PLC containers
HMI containers
Sensor containers
Valve containers
Bottle factory container
Network telemetry container
OT Redis
OT Streamlit dashboard

The OT dashboard opens at:

http://localhost:8501
B. AI / Django Side

The AI side uses Docker images hosted on GitHub Container Registry.

It includes:

Django web dashboard
Django alert consumer
AI Redis
Stage 1/2 alert replay producer
Stage 3 IR/RAG service

The Django dashboard opens at:

http://localhost:8000

The Stage 3 health endpoint is:

http://localhost:8001/health
2. Important Deployment Mode

The official acceptance testing mode uses dataset-based alert replay.

The flow is:

Stage 1/2 replay producer
→ AI Redis
→ Django consumer
→ SQLite database
→ Django dashboard
→ Stage 3 IR/RAG service

The live OT prediction flow is not used as the official testing mode. It is considered experimental/future work.

The OT simulator still runs and is shown through the OT dashboard.

3. Requirements

Before running the system, make sure the laptop has:

Docker Desktop installed and running
WSL/Ubuntu installed
Git installed
Python 3 installed inside Ubuntu
Internet connection
A valid Groq API key

Run all commands from Ubuntu/WSL, not Git Bash.

4. Clone the Repository

Open Ubuntu and run:

git clone https://github.com/SomayaElgendy/capstone-ot-anomaly-detection-deployment.git
cd capstone-ot-anomaly-detection-deployment
5. Create the Environment File

Copy the example file:

cp .env.example .env

Open .env:

nano .env

Add your real Groq API key:

GROQ_API_KEY=your_real_groq_api_key_here
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1,0.0.0.0

Save and exit:

CTRL + O
Enter
CTRL + X

Never upload the real .env file to GitHub.

6. Pull Docker Images

The AI images are already built and hosted on GitHub Container Registry.

Pull them using:

./pull_images.sh

This avoids rebuilding the heavy Stage 3 image locally.

7. Start the Full System

Run:

./deploy_all.sh

This script starts:

OT simulator containers
OT dashboard
AI Redis
Django dashboard
Django alert consumer
Stage 1/2 alert producer
Stage 3 IR/RAG service

After it finishes, open:

OT Dashboard:      http://localhost:8501
Django Dashboard:  http://localhost:8000
Stage 3 Health:    http://localhost:8001/health
8. Replay Alerts

If you want alerts to appear live again on the Django dashboard, run:

./replay.sh

This restarts only the Stage 1/2 producer.

The dashboard should show new alerts appearing.

To stop only the alert replay producer:

./stop_replay.sh

This does not stop Django, Stage 3, Redis, or the OT simulator.

9. Generate an Incident Response Report

From the Django dashboard:

Log in as a security user.
Open an alert.
Click Generate IR.
Wait for Stage 3 to generate the report.

The generated report should appear in the UI.

You can also download it as:

Markdown
Word document
10. Chat with Stage 3

From the alert detail page:

Type a question in the chat box.
Send the message.
Wait for the Stage 3 response.

Django sends the alert context to Stage 3, and Stage 3 returns the answer.

11. Stop the Full System

Run:

./stop_all.sh

This stops:

AI containers
Django containers
Stage 3 container
AI Redis
OT simulator containers
OT Redis
OT dashboard

Verify with:

docker ps

There should be no running project containers.

12. Useful Commands

Check running containers:

docker ps

Check AI services:

docker compose -f docker-compose.ghcr.yml ps

View Django consumer logs:

docker compose -f docker-compose.ghcr.yml logs -f django-consumer

View Stage 3 logs:

docker logs capstone-stage3 --tail 100

Test Stage 3 from the host:

curl http://localhost:8001/health

Test Stage 3 from inside Django:

docker exec -it capstone-django-web python -c "import requests; print(requests.get('http://stage3:8001/health', timeout=10).text)"

Expected output:

{"status":"ok"}
13. Troubleshooting
Problem: Stage 3 health does not open

Check:

docker compose -f docker-compose.ghcr.yml ps
docker logs capstone-stage3 --tail 100
Problem: Django cannot reach Stage 3

Restart AI services:

docker compose -f docker-compose.ghcr.yml down --remove-orphans
docker compose -f docker-compose.ghcr.yml up -d

Do not manually start individual containers from Docker Desktop.

Problem: Alerts are consumed but not shown on the dashboard

Make sure both Django containers share the same SQLite database volume:

./backend/backend/db.sqlite3:/app/backend/db.sqlite3

Then restart:

docker compose -f docker-compose.ghcr.yml down --remove-orphans
docker compose -f docker-compose.ghcr.yml up -d
Problem: Port already in use

Check running containers:

docker ps

Stop the full system:

./stop_all.sh

Then start again:

./deploy_all.sh
Problem: Stage 3 build takes too long

Do not build Stage 3 locally for acceptance testing. Use:

./pull_images.sh
14. Final Acceptance Testing Flow

Use this sequence:

./pull_images.sh
./deploy_all.sh
./replay.sh

Then test:

OT dashboard opens at localhost:8501
Django dashboard opens at localhost:8000
Alerts appear on dashboard
IR generation works
Chat works
Report download works
./stop_all.sh stops the system cleanly
