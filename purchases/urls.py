from django.urls import path

from . import views

app_name = "purchases"

urlpatterns = [
    path("", views.purchase_list, name="list"),
    path("new/", views.purchase_create, name="add"),
    path("new/search/", views.purchase_search, name="search"),
    path("new/checkout/", views.purchase_checkout, name="checkout"),
    path("<int:pk>/", views.purchase_detail, name="detail"),
]
