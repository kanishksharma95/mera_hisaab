from django.urls import path

from . import views

app_name = "products"

urlpatterns = [
    path("", views.product_list, name="list"),
    path("add/", views.product_create, name="add"),
    path("<int:pk>/", views.product_detail, name="detail"),
    path("<int:pk>/edit/", views.product_edit, name="edit"),
    path("<int:pk>/toggle/", views.product_toggle, name="toggle"),
    # Categories live under /products/categories/
    path("categories/", views.category_list, name="category_list"),
    path("categories/add/", views.category_create, name="category_add"),
    path("categories/<int:pk>/edit/", views.category_edit, name="category_edit"),
    path("categories/<int:pk>/toggle/", views.category_toggle, name="category_toggle"),
]
