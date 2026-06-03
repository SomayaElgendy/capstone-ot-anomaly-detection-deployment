import os

from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Alert


def _main_score(a: Alert) -> float:
    return max(
        float(a.network_anomaly_score or 0.0),
        float(a.process_anomaly_score or 0.0),
    )


def _build_fallback_summary(a: Alert) -> str:
    return (
        f"{a.predicted_attack} detected by the AI pipeline "
        f"with classifier confidence {float(a.classifier_confidence or 0.0):.3f}. "
        f"Network anomaly score is {float(a.network_anomaly_score or 0.0):.3f}, "
        f"and process anomaly score is {float(a.process_anomaly_score or 0.0):.3f}. "
        f"The alert window is from {a.window_start_time.isoformat()} to {a.window_end_time.isoformat()}."
    )


def _build_prompt(a: Alert) -> str:
    raw_metadata = a.extra or {}

    return f"""
You are an ICS SOC analyst.

Write a short alert summary for the dashboard.
The summary must be:
- natural and professional
- grounded only in the provided Stage 2 alert data
- 2 to 4 short sentences maximum
- concise and useful for a security specialist
- not a full incident response report
- free of assumptions that are not explicitly supported by the input

Use only the following data:

Predicted attack: {a.predicted_attack}
Classifier confidence: {float(a.classifier_confidence or 0.0)}
Network anomaly score: {float(a.network_anomaly_score or 0.0)}
Process anomaly score: {float(a.process_anomaly_score or 0.0)}
Main anomaly score: {_main_score(a)}
Window start time: {a.window_start_time.isoformat() if a.window_start_time else "N/A"}
Window end time: {a.window_end_time.isoformat() if a.window_end_time else "N/A"}
Technique ID: {a.technique_id or "N/A"}
Status: {a.status}
Raw metadata: {raw_metadata}

Do not invent attacker behavior, affected hosts, device IDs, network paths, severity, or recommended actions.
Return only the summary text.
""".strip()


def _generate_groq_summary(a: Alert) -> str:
    api_key = os.getenv("GROQ_API_KEY", "").strip()

    if not api_key:
        return _build_fallback_summary(a)

    try:
        from groq import Groq

        client = Groq(api_key=api_key)
        response = client.chat.completions.create(
            model=os.getenv("CHAT_MODEL", "llama-3.3-70b-versatile"),
            messages=[
                {
                    "role": "system",
                    "content": "You are a precise industrial cybersecurity analyst.",
                },
                {
                    "role": "user",
                    "content": _build_prompt(a),
                },
            ],
            temperature=0.2,
            max_tokens=120,
        )

        content = response.choices[0].message.content if response.choices else ""
        summary = (content or "").strip()

        if not summary:
            return _build_fallback_summary(a)

        return summary

    except Exception:
        return _build_fallback_summary(a)


@receiver(post_save, sender=Alert)
def generate_summary_on_create(sender, instance: Alert, created: bool, **kwargs):
    if not created:
        return

    if instance.llm_response:
        return

    summary = _generate_groq_summary(instance)
    Alert.objects.filter(id=instance.id).update(llm_response=summary)