from rest_framework import serializers
from alerts.models import Alert

class AlertSerializer(serializers.ModelSerializer):
    class Meta:
        model = Alert
        fields = ['id', 'title', 'severity', 'llm_response', 'recommended_actions',
                  'attack_label', 'anomaly_score', 'device_id', 'timestamp', 'created_at']