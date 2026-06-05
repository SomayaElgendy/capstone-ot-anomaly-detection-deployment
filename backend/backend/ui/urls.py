from django.urls import path
from . import views

app_name = "ui"

urlpatterns = [
    path("", views.home, name="home"),
    path("request-service/", views.request_service, name="request_service"),

    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),

    path("dashboard/", views.dashboard, name="dashboard"),
    path("alerts/<int:alert_id>/", views.alert_detail, name="alert_detail"),
    path("ot-overview/", views.ot_overview, name="ot_overview"),
    path("ui-data/alerts/", views.ui_alerts_data, name="ui_alerts_data"),
    path("ui-data/alerts/<int:alert_id>/", views.ui_alert_detail_data, name="ui_alert_detail_data"),
    path("ui-data/chat/", views.ui_chat, name="ui_chat"),
    path("ui-data/alerts/<int:alert_id>/ack/", views.ui_ack_alert, name="ui_ack_alert"),
    path("ui-data/report/", views.ui_generate_report, name="ui_generate_report"),
    path("ui-data/report/<str:run_id>/download/<str:file_format>/", views.ui_download_report, name="ui_download_report"),
    path("forgot-password/", views.forgot_password, name="forgot_password"),
]
