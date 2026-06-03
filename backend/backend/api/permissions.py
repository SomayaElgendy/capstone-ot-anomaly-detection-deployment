from functools import wraps
from rest_framework.response import Response
from rest_framework import status


def require_permission(permission_check):
    """
    Decorator to check user permissions
    Usage: @require_permission('can_view_alerts')
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return Response(
                    {'error': 'Authentication required'},
                    status=status.HTTP_401_UNAUTHORIZED
                )
            
            if not getattr(request.user, permission_check, False):
                return Response(
                    {'error': 'Permission denied'},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator