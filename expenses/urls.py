from django.urls import path

from . import views

app_name = "expenses"

urlpatterns = [
    path("", views.expense_list, name="list"),
    path("add/", views.expense_create, name="add"),
    path("categories/", views.category_list, name="category_list"),
    path("categories/add/", views.category_create, name="category_add"),
    path("categories/<int:pk>/edit/", views.category_edit, name="category_edit"),
    path("categories/<int:pk>/toggle/", views.category_toggle, name="category_toggle"),
    path("export/csv/", views.expense_export_csv, name="export_csv"),
]

