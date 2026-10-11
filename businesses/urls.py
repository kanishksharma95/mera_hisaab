from django.urls import path

from . import views

app_name = "businesses"

urlpatterns = [
    path("onboarding/", views.onboarding, name="onboarding"),
    path(
        "app/switch-business/<int:business_id>/",
        views.switch_business,
        name="switch_business",
    ),
    path("team/", views.team_list, name="team_list"),
    path("team/add/", views.employee_create, name="employee_create"),
    path("team/<int:membership_id>/edit/", views.employee_edit, name="employee_edit"),
    path("team/<int:membership_id>/delete/", views.employee_delete, name="employee_delete"),
    path("settings/", views.business_settings, name="settings"),
]


