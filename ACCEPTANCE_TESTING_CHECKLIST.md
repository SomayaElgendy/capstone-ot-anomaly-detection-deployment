# Acceptance Testing Checklist

This checklist is used to verify that the deployed OT anomaly detection system works correctly on a tester machine.

---

## 1. Environment Setup

Confirm the machine has:

- Docker Desktop installed and running
- WSL/Ubuntu installed
- Git installed
- Python 3 available in Ubuntu
- Internet connection
- Valid Groq API key

---

## 2. Repository Setup

Run:

```bash
git clone https://github.com/SomayaElgendy/capstone-ot-anomaly-detection-deployment.git
cd capstone-ot-anomaly-detection-deployment
cp .env.example .env
nano .env


Add:

GROQ_API_KEY=your_real_groq_api_key_here
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1,0.0.0.0
3. Pull Docker Images

Run:

./pull_images.sh

Expected:

Django image pulls successfully
Stage 1/2 producer image pulls successfully
Stage 3 image pulls successfully
4. Start Full System

Run:

./deploy_all.sh

Expected:

OT containers start
AI containers start
No port conflict errors

Open:

http://localhost:8501
http://localhost:8000
http://localhost:8001/health

Expected:

OT dashboard opens
Django dashboard opens
Stage 3 health returns {"status":"ok"}
5. Replay Alerts

Run:

./replay.sh

Expected:

Stage 1/2 producer starts
Django consumer receives alerts
Alerts appear on the Django dashboard

Optional log check:

docker compose -f docker-compose.ghcr.yml logs -f django-consumer
6. Generate IR Report

From the Django dashboard:

Open an alert.
Click Generate IR.
Wait for Stage 3 to respond.

Expected:

Incident response report appears.
Run ID is stored.
No timeout or connection error appears.
7. Chat Test

From the alert detail page:

Type a question.
Send the message.

Expected:

Stage 3 returns a relevant response.
No connection error appears.
8. Download Report

Try downloading:

Markdown report
Word report

Expected:

Files download successfully.
Content matches the generated incident response.
9. Stop Replay Only

Run:

./stop_replay.sh

Expected:

Only the Stage 1/2 producer stops.
Django, Redis, Stage 3, and OT remain running.
10. Stop Full System

Run:

./stop_all.sh

Then:

docker ps

Expected:

No project containers are running.

```text

