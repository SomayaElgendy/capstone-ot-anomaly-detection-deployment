import os
import re
import requests


DJANGO_BASE = os.getenv("DJANGO_BASE", "http://127.0.0.1:8000")
STAGE3_BASE = os.getenv("STAGE3_BASE", "http://127.0.0.1:8001")

USERNAME = os.getenv("DJANGO_USERNAME", "YOUR_USERNAME")
PASSWORD = os.getenv("DJANGO_PASSWORD", "YOUR_PASSWORD")

RUN_STAGE3_ACTIONS = os.getenv("RUN_STAGE3_ACTIONS", "0") == "1"


def extract_csrf(html):
    match = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', html)
    return match.group(1) if match else None


def test_stage3_health():
    response = requests.get(f"{STAGE3_BASE}/health", timeout=10)

    assert response.status_code == 200
    assert response.json().get("status") == "ok"


def test_django_dashboard_alert_flow():
    session = requests.Session()

    login_page = session.get(f"{DJANGO_BASE}/login/", timeout=10)
    assert login_page.status_code == 200

    csrf = extract_csrf(login_page.text) or session.cookies.get("csrftoken")
    assert csrf is not None

    login_response = session.post(
        f"{DJANGO_BASE}/login/",
        data={
            "username": USERNAME,
            "password": PASSWORD,
            "csrfmiddlewaretoken": csrf,
        },
        headers={"Referer": f"{DJANGO_BASE}/login/"},
        timeout=10,
        allow_redirects=False,
    )

    assert login_response.status_code in [302, 303]

    alerts_response = session.get(f"{DJANGO_BASE}/ui-data/alerts/", timeout=10)
    assert alerts_response.status_code == 200

    alerts = alerts_response.json()
    assert isinstance(alerts, list)
    assert len(alerts) > 0

    alert_id = alerts[0]["id"]

    detail_response = session.get(
        f"{DJANGO_BASE}/ui-data/alerts/{alert_id}/",
        timeout=10,
    )

    assert detail_response.status_code == 200

    detail = detail_response.json()

    required_fields = [
        "id",
        "predicted_attack",
        "classifier_confidence",
        "network_anomaly_score",
        "process_anomaly_score",
        "window_start_time",
        "window_end_time",
        "technique_id",
        "stage2_alert_json",
    ]

    for field in required_fields:
        assert field in detail

    csrf = session.cookies.get("csrftoken", csrf)

    ack_response = session.post(
        f"{DJANGO_BASE}/ui-data/alerts/{alert_id}/ack/",
        headers={
            "X-CSRFToken": csrf,
            "Referer": f"{DJANGO_BASE}/alerts/{alert_id}/",
        },
        timeout=10,
    )

    assert ack_response.status_code == 200
    assert ack_response.json().get("status") == "Acknowledged"


def test_optional_stage3_report_and_chat_flow():
    if not RUN_STAGE3_ACTIONS:
        return

    session = requests.Session()

    login_page = session.get(f"{DJANGO_BASE}/login/", timeout=10)
    csrf = extract_csrf(login_page.text) or session.cookies.get("csrftoken")

    login_response = session.post(
        f"{DJANGO_BASE}/login/",
        data={
            "username": USERNAME,
            "password": PASSWORD,
            "csrfmiddlewaretoken": csrf,
        },
        headers={"Referer": f"{DJANGO_BASE}/login/"},
        timeout=10,
        allow_redirects=False,
    )

    assert login_response.status_code in [302, 303]

    alerts_response = session.get(f"{DJANGO_BASE}/ui-data/alerts/", timeout=10)
    alerts = alerts_response.json()
    assert len(alerts) > 0

    alert_id = alerts[0]["id"]
    csrf = session.cookies.get("csrftoken", csrf)

    report_response = session.post(
        f"{DJANGO_BASE}/ui-data/report/",
        json={"alert_id": alert_id},
        headers={
            "X-CSRFToken": csrf,
            "Referer": f"{DJANGO_BASE}/alerts/{alert_id}/",
        },
        timeout=240,
    )

    assert report_response.status_code == 200
    assert report_response.json().get("report")

    chat_response = session.post(
        f"{DJANGO_BASE}/ui-data/chat/",
        json={
            "alert_id": alert_id,
            "message": "What does this alert mean?",
        },
        headers={
            "X-CSRFToken": csrf,
            "Referer": f"{DJANGO_BASE}/alerts/{alert_id}/",
        },
        timeout=120,
    )

    assert chat_response.status_code == 200
    assert chat_response.json().get("reply")