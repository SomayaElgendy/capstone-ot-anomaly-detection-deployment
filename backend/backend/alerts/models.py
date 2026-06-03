from django.db import models
from django.conf import settings


class Alert(models.Model):
    """Stores Stage 2 AI alerts."""

    predicted_attack = models.CharField(max_length=120)
    classifier_confidence = models.FloatField(default=0.0)

    network_anomaly_score = models.FloatField(default=0.0)
    process_anomaly_score = models.FloatField(default=0.0)

    window_start_time = models.DateTimeField()
    window_end_time = models.DateTimeField()

    technique_id = models.CharField(max_length=30, blank=True, default="")

    llm_response = models.TextField(blank=True, default="")
    recommended_actions = models.JSONField(blank=True, default=dict)
    full_report = models.TextField(blank=True, default="")

    extra = models.JSONField(blank=True, default=dict)

    created_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, default="Pending")

    acknowledged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL
    )
    acknowledged_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.predicted_attack} ({self.technique_id})"