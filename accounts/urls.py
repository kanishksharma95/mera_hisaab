from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("register/", views.RegisterView.as_view(), name="register"),
    path("login/", views.MeraLoginView.as_view(), name="login"),
    path("logout/", views.MeraLogoutView.as_view(), name="logout"),
    path("profile/", views.profile, name="profile"),
    path(
        "password/change/",
        views.MeraPasswordChangeView.as_view(),
        name="password_change",
    ),
    path(
        "password/reset/",
        views.MeraPasswordResetView.as_view(),
        name="password_reset",
    ),
    path(
        "password/reset/done/",
        views.MeraPasswordResetDoneView.as_view(),
        name="password_reset_done",
    ),
    path(
        "password/reset/confirm/<uidb64>/<token>/",
        views.MeraPasswordResetConfirmView.as_view(),
        name="password_reset_confirm",
    ),
    path(
        "password/reset/complete/",
        views.MeraPasswordResetCompleteView.as_view(),
        name="password_reset_complete",
    ),
]
