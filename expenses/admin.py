from django.contrib import admin

from .models import Expense, ExpenseCategory


@admin.register(ExpenseCategory)
class ExpenseCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "business", "sort_order", "is_active")
    list_filter = ("is_active", "business")
    search_fields = ("name", "business__name")
    autocomplete_fields = ("business",)


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ("business", "category", "amount", "method", "spent_on")
    list_filter = ("business", "category", "spent_on")
    search_fields = ("business__name", "category__name", "note")
    autocomplete_fields = ("business", "category", "method", "created_by")
    date_hierarchy = "spent_on"
