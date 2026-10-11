from django.urls import path

from . import views

app_name = "customers"

urlpatterns = [
    path("", views.customer_list, name="list"),
    path("add/", views.customer_create, name="add"),
    path("<int:pk>/", views.customer_detail, name="detail"),
    path("<int:pk>/edit/", views.customer_edit, name="edit"),
    path("<int:pk>/payment/", views.record_payment_view, name="payment"),
    path("<int:pk>/udhaar/", views.add_udhaar_view, name="add_udhaar"),
    path("export/csv/", views.customer_export_csv, name="export_csv"),
]

