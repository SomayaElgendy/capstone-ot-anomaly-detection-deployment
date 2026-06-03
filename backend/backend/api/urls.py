from django.urls import path
from . import views
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

urlpatterns = [
    path('alerts/', views.get_alerts, name='get_alerts'),
    path('chat/', views.chat_with_llm, name='chat_llm'),
    path('models/', views.manage_models, name='manage_models'),
    path('users/create/', views.create_user, name='create_user'),
    path('token/', TokenObtainPairView.as_view(), name='token_obtain'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
]
