from .models import Alert

def alert_to_ui_dict(a: Alert) -> dict:
    return {
        "id": a.id,
        "title": a.title,
        "severity": a.severity,
        "attack_label": a.attack_label,
        "anomaly_score": a.anomaly_score,
        "device_id": a.device_id,
        "pipeline_time": a.timestamp,
        "created_at": a.created_at,
        "status": a.status,
        "ack_by": getattr(a.acknowledged_by, "username", None),
        "ack_at": a.acknowledged_at,
        "summary": a.llm_response,
        "full_report": a.full_report,
        "recommended_actions": a.recommended_actions,
        "extra": getattr(a, "extra", {}),
    }