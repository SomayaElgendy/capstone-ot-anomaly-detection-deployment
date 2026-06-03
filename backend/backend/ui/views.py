from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.utils import timezone
import json, requests
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_protect
from alerts.models import Alert
from django.conf import settings
import redis
from django.contrib import messages
from .forms import ServiceRequestForm
from django.core.mail import send_mail
from functools import wraps

ROLE_SECURITY = "security_specialist"


def get_user_roles(user):
    roles = set()

    if hasattr(user, "role") and user.role:
        roles.add(str(user.role).lower())

    roles.update(name.lower() for name in user.groups.values_list("name", flat=True))

    return roles


def user_is_django_admin(user):
    return user.is_authenticated and (user.is_superuser or user.is_staff)


def user_has_security_access(user):
    if not user.is_authenticated:
        return False

    roles = get_user_roles(user)
    return ROLE_SECURITY in roles


def require_security(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("ui:login")

        if not user_has_security_access(request.user):
            return render(request, "ui/403.html", status=403)

        return view_func(request, *args, **kwargs)

    return wrapper

def home(request):
    return render(request, "ui/home.html")

def request_service(request):
    if request.method == "POST":
        form = ServiceRequestForm(request.POST)

        if form.is_valid():
            form.save()
            messages.success(request, "Your service request has been submitted successfully. We will contact you soon.")
            return redirect("ui:request_service")
    else:
        form = ServiceRequestForm()

    return render(request, "ui/request_service.html", {"form": form})

def login_view(request):
    if request.user.is_authenticated:
        if user_is_django_admin(request.user):
            return redirect("/admin/")

        if user_has_security_access(request.user):
            return redirect("ui:dashboard")

        return redirect("ui:home")

    if request.method == "POST":
        username = request.POST.get("username", "")
        password = request.POST.get("password", "")
        user = authenticate(request, username=username, password=password)

        if user:
            login(request, user)

            if user_is_django_admin(user):
                return redirect("/admin/")

            if user_has_security_access(user):
                return redirect("ui:dashboard")

            return redirect("ui:home")

        return render(request, "ui/login.html", {"error": "Invalid credentials"})

    return render(request, "ui/login.html")

def logout_view(request):
    logout(request)
    return redirect("ui:home")


@login_required
@require_security
def dashboard(request):
    return render(request, "ui/dashboard.html")

@login_required
@require_security
def alert_detail(request, alert_id: int):
    return render(request, "ui/alert_detail.html", {"alert_id": alert_id})

@login_required
@require_security
def ot_overview(request):
    return render(request, "ui/ot_dashboard_embed.html", {
    "streamlit_url": getattr(settings, "OT_STREAMLIT_URL", "http://127.0.0.1:8501")})

@login_required
@require_security
def ui_alerts_data(request):
    qs = Alert.objects.order_by("-created_at")[:50]
    data = []

    for a in qs:
        data.append({
            "id": a.id,
            "predicted_attack": a.predicted_attack,
            "classifier_confidence": float(a.classifier_confidence or 0),
            "network_anomaly_score": float(a.network_anomaly_score or 0),
            "process_anomaly_score": float(a.process_anomaly_score or 0),
            "window_start_time": a.window_start_time.isoformat() if a.window_start_time else None,
            "window_end_time": a.window_end_time.isoformat() if a.window_end_time else None,
            "technique_id": a.technique_id,
            "is_apt": a.extra.get("is_apt", False) if a.extra else False,
            "status": a.status or "Pending",
            "created_at": a.created_at.isoformat() if a.created_at else None,
        })

    return JsonResponse(data, safe=False)

@login_required
@require_security
def ui_alert_detail_data(request, alert_id: int):
    a = get_object_or_404(Alert, id=alert_id)

    stage2_alert_json = {
        "predicted_attack": a.predicted_attack,
        "classifier_confidence": float(a.classifier_confidence or 0),
        "network_anomaly_score": float(a.network_anomaly_score or 0),
        "process_anomaly_score": float(a.process_anomaly_score or 0),
        "window_start_time": a.window_start_time.isoformat() if a.window_start_time else None,
        "window_end_time": a.window_end_time.isoformat() if a.window_end_time else None,
        "technique_id": a.technique_id,
    }

    extra = a.extra or {}

    return JsonResponse({
        "id": a.id,
        "status": a.status or "Pending",
        "created_at": a.created_at.isoformat() if a.created_at else None,
        **stage2_alert_json,
        "stage2_alert_json": stage2_alert_json,
        "incident_response": a.llm_response or "",
        "full_report": a.full_report or "",
        "stage3_run_id": extra.get("stage3_run_id"),
        "stage3_grade": extra.get("stage3_grade"),
        "stage3_score": extra.get("stage3_score"),
    })
@require_POST
@csrf_protect
@login_required
@require_security
def ui_chat(request):
    """
    Session-auth endpoint used by the UI only.
    Calls FastAPI /chat from server-side.
    """
    try:
        body = json.loads(request.body.decode("utf-8"))
    except Exception:
        return JsonResponse({"error": "Invalid JSON body"}, status=400)

    alert_id = body.get("alert_id")
    user_msg = (body.get("message") or "").strip()

    if not alert_id or not user_msg:
        return JsonResponse({"error": "alert_id and message are required"}, status=400)

    # Load alert from DB to build context
    try:
        a = Alert.objects.get(id=alert_id)
    except Alert.DoesNotExist:
        return JsonResponse({"error": "Alert not found"}, status=404)

    payload = {
        "message": user_msg,
        "context": {
        "label": normalize_attack_label(
            getattr(a, "predicted_attack", None)
            or getattr(a, "title", None)
            or "unknown"
        ),
        "attack_label": normalize_attack_label(
            getattr(a, "predicted_attack", None)
            or getattr(a, "title", None)
            or "unknown"
        ),
        "severity": getattr(a, "severity", "unknown"),
        "anomaly_score": max(
            float(getattr(a, "network_anomaly_score", 0) or 0),
            float(getattr(a, "process_anomaly_score", 0) or 0),
        ),
        "status": getattr(a, "status", "unknown"),
        "created_at": (
            a.created_at.isoformat()
            if getattr(a, "created_at", None)
            else ""
        ),
        "recommended_actions": {},
        "incident_summary": getattr(a, "summary", ""),
        "full_report": getattr(a, "incident_report", ""),
    }
    }

    headers = {"Content-Type": "application/json"}
    if getattr(settings, "RAG_SERVICE_TOKEN", ""):
        headers["Authorization"] = f"Bearer {settings.RAG_SERVICE_TOKEN}"

    chat_url = getattr(settings, "RAG_CHAT_ENDPOINT", None) or settings.RAG_ENDPOINT

    try:
        r = requests.post(chat_url, json=payload, headers=headers, timeout=300)
    except requests.RequestException as e:
        return JsonResponse({"error": f"Chat service request failed: {str(e)}"}, status=502)

    if r.status_code != 200:
        return JsonResponse({
            "error": "Chat service error",
            "status": r.status_code,
            "details_text": r.text[:1000],
        }, status=502)

    try:
        data = r.json()
    except Exception:
        return JsonResponse({"error": "Invalid JSON from chat service"}, status=502)

    reply = data.get("reply")
    if not reply:
        return JsonResponse({"error": "Unexpected chat response format", "raw": data}, status=502)

    return JsonResponse({"reply": reply})


@require_POST
@csrf_protect
@login_required
@require_security
def ui_ack_alert(request, alert_id: int):
    a = get_object_or_404(Alert, id=alert_id)
    a.status = "Acknowledged"
    a.acknowledged_by = request.user
    a.acknowledged_at = timezone.now()
    a.save()
    return JsonResponse({"ok": True, "status": a.status})


def normalize_attack_label(label: str) -> str:
    if not label:
        return "unknown"

    value = label.strip().lower().replace("-", "_").replace(" ", "_")

    mapping = {
        "ip_scan": "ip_scan",
        "mitm": "mitm",
        "dos": "dos",
        "ddos": "dos",
        "ransomware": "ransomware",
        "command_injection": "command_injection",
    }
    return mapping.get(value, value)


def map_alert_to_stage3_payload(a):
    extra = a.extra or {}

    predicted_attack = (
        extra.get("predicted_attack")
        or getattr(a, "predicted_attack", None)
        or getattr(a, "title", None)
        or "unknown"
    )

    confidence = (
        extra.get("classifier_confidence")
        or extra.get("confidence")
        or getattr(a, "classifier_confidence", None)
        or 0.0
    )

    network_score = (
        extra.get("network_anomaly_score")
        or getattr(a, "network_anomaly_score", None)
        or 0.0
    )

    process_score = (
        extra.get("process_anomaly_score")
        or getattr(a, "process_anomaly_score", None)
        or 0.0
    )

    window_start = (
        extra.get("window_start_time")
        or getattr(a, "window_start_time", None)
        or getattr(a, "pipeline_time", None)
        or getattr(a, "created_at", None)
        or getattr(a, "timestamp", None)
    )

    window_end = (
        extra.get("window_end_time")
        or getattr(a, "window_end_time", None)
        or getattr(a, "pipeline_time", None)
        or getattr(a, "created_at", None)
        or getattr(a, "timestamp", None)
    )

    if window_start and hasattr(window_start, "isoformat"):
        window_start = window_start.isoformat()

    if window_end and hasattr(window_end, "isoformat"):
        window_end = window_end.isoformat()

    return {
        "predicted_attack": str(predicted_attack or "unknown").strip(),
        "classifier_confidence": float(confidence or 0.0),
        "network_anomaly_score": float(network_score or 0.0),
        "process_anomaly_score": float(process_score or 0.0),
        "window_start_time": window_start or "",
        "window_end_time": window_end or "",
        "technique_id": extra.get("technique_id") or getattr(a, "technique_id", None),
    }

@require_POST
@login_required
@require_security
def ui_generate_report(request):
    try:
        body = json.loads(request.body.decode("utf-8"))
    except Exception:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    alert_id = body.get("alert_id")
    if not alert_id:
        return JsonResponse({"error": "alert_id is required"}, status=400)

    try:
        a = Alert.objects.get(id=alert_id)
    except Alert.DoesNotExist:
        return JsonResponse({"error": "Alert not found"}, status=404)

    payload = map_alert_to_stage3_payload(a)

    ir_url = getattr(settings, "RAG_ENDPOINT", "http://localhost:8001/generate-ir")

    headers = {"Content-Type": "application/json"}
    if getattr(settings, "RAG_SERVICE_TOKEN", ""):
        headers["Authorization"] = f"Bearer {settings.RAG_SERVICE_TOKEN}"

    try:
        r = requests.post(ir_url, json=payload, headers=headers, timeout=600)
    except requests.RequestException as e:
        return JsonResponse({"error": f"Report service unreachable: {str(e)}"}, status=502)

    if r.status_code != 200:
        return JsonResponse(
            {
                "error": "Report service error",
                "status": r.status_code,
                "details": r.text[:1000],
            },
            status=502,
        )

    try:
        data = r.json()
    except Exception:
        return JsonResponse({"error": "Invalid JSON from report service"}, status=502)

    report = data.get("reply") or ""
    if not report:
        return JsonResponse({"error": "Invalid report response", "raw": data}, status=502)

    stage3_run_id = data.get("run_id")

    extra = a.extra or {}
    extra["stage3_run_id"] = stage3_run_id
    extra["stage3_grade"] = data.get("grade")
    extra["stage3_score"] = data.get("score")

    a.extra = extra
    a.full_report = report
    a.llm_response = report[:1000]
    a.save(update_fields=["full_report", "llm_response", "extra"])

    return JsonResponse({
        "report": report,
        "grade": data.get("grade"),
        "score": data.get("score"),
        "run_id": data.get("run_id"),
    })

@login_required
@require_security
def ui_download_report(request, run_id: str, file_format: str):
    if file_format not in ["md", "docx"]:
        return JsonResponse({"error": "Invalid file format"}, status=400)

    stage3_base_url = getattr(settings, "STAGE3_BASE_URL", "http://127.0.0.1:8001")
    download_url = f"{stage3_base_url}/download-ir/{run_id}/{file_format}"

    headers = {}
    if getattr(settings, "RAG_SERVICE_TOKEN", ""):
        headers["Authorization"] = f"Bearer {settings.RAG_SERVICE_TOKEN}"

    try:
        r = requests.get(download_url, headers=headers, timeout=60)
    except requests.RequestException as e:
        return JsonResponse(
            {"error": f"Download service unreachable: {str(e)}"},
            status=502,
        )

    if r.status_code != 200:
        return JsonResponse(
            {
                "error": "Download service error",
                "status": r.status_code,
                "details": r.text[:1000],
            },
            status=502,
        )

    if file_format == "md":
        content_type = "text/markdown"
        filename = f"{run_id}.md"
    else:
        content_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        filename = f"{run_id}.docx"

    response = HttpResponse(r.content, content_type=content_type)
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response

# @login_required
# @require_security
# def ui_ot_state_data(request):
#     r = redis.Redis(
#         host=getattr(settings, "OT_REDIS_HOST", "127.0.0.1"),
#         port=getattr(settings, "OT_REDIS_PORT", 6379),
#         decode_responses=True,
#     )

#     entry = r.xrevrange("hil:telemetry", count=1)

#     if not entry:
#         return JsonResponse({"error": "No OT state found."}, status=404)

#     _, data = entry[0]

#     # Parse validation
#     validation = {}
#     if data.get("_validation"):
#         try:
#             validation = json.loads(data["_validation"])
#         except Exception:
#             validation = {"raw": data["_validation"]}

#     response_data = {
#         "timestamp": data.get("timestamp"),
#         "timestamp_iso": data.get("timestamp_iso"),
#         "timestamp_unix_ms": data.get("timestamp_unix_ms"),

#         "tank_level": int(float(data.get("tank_level_value", 0))),
#         "tank_input_valve": int(data.get("tank_input_valve_state", 0)),
#         "tank_output_valve": int(data.get("tank_output_valve_state", 0)),
#         "bottle_level": int(float(data.get("bottle_level_value", 0))),
#         "bottle_distance_to_filler": int(float(data.get("bottle_distance_to_filler_value", 0))),
#         "conveyor_belt_engine": int(data.get("conveyor_belt_engine_state", 0)),
#         "tank_output_flow": float(data.get("tank_output_flow_value", 0.0)),

#         "validation": validation,
#     }

#     return JsonResponse(response_data)

