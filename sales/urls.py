from django.urls import path

from . import views

app_name = "sales"

urlpatterns = [
    path("", views.sale_list, name="list"),
    path("pos/", views.pos, name="pos"),
    path("pos/search/", views.pos_search, name="pos_search"),
    path("pos/checkout/", views.pos_checkout, name="pos_checkout"),
    path("<int:pk>/", views.invoice, name="invoice"),
    path("<int:pk>/pdf/", views.invoice_pdf, name="invoice_pdf"),
    path("<int:pk>/thermal/", views.invoice_thermal, name="thermal"),
    path("export/csv/", views.sale_export_csv, name="export_csv"),
]


