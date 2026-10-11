from django.urls import path

from . import views

app_name = "inventory"

urlpatterns = [
    path("", views.inventory_list, name="list"),
    path("<int:product_pk>/adjust/", views.stock_adjust, name="adjust"),
]
