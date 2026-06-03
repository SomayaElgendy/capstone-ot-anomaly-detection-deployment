from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from .permissions import require_permission
from alerts.models import Alert
from .serializers import AlertSerializer
from django.utils import timezone
from datetime import timedelta




@api_view(['GET'])
@permission_classes([IsAuthenticated])
@require_permission('can_view_alerts')
def get_alerts(request):
    """Returns latest alerts (last 10 seconds for real-time polling)"""
    ten_seconds_ago = timezone.now() - timedelta(seconds=10)
    alerts = Alert.objects.filter(created_at__gte=ten_seconds_ago)
    serializer = AlertSerializer(alerts, many=True)
    return Response(serializer.data)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
@require_permission('can_chat_with_llm')
def chat_with_llm(request):
    """FR14: LLM chat (Security Specialist only)"""
    # Stub 
    return Response({
        'message': 'LLM chat endpoint - will integrate later',
        'user_role': request.user.role
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@require_permission('can_manage_ai_models')
def manage_models(request):
    """FR5: AI models management (AI Engineer only)"""
    # Stub
    return Response({
        'message': 'AI models endpoint - will implement later',
        'user_role': request.user.role
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@require_permission('can_manage_accounts')
def create_user(request):
    """FR2: Account granting (Admin only)"""
    # Stub
    return Response({
        'message': 'User creation endpoint - admin only',
        'user_role': request.user.role
    })



