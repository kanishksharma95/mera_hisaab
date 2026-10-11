from django.urls import path

from . import views

app_name = "suppliers"

urlpatterns = [
    path("", views.supplier_list, name="list"),
    path("add/", views.supplier_create, name="add"),
    path("<int:pk>/", views.supplier_detail, name="detail"),
    path("<int:pk>/edit/", views.supplier_edit, name="edit"),
    path("<int:pk>/payment/", views.supplier_payment_view, name="payment"),
]
