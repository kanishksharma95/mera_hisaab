from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.home, name="home"),
    path("app/", views.dashboard, name="dashboard"),
    path("app/reports/", views.reports, name="reports"),
    path("app/assistant/", views.ai_assistant, name="ai_assistant"),
    path("app/assistant/chat/", views.ai_chat, name="ai_chat"),
]
