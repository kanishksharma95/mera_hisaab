from django.contrib import admin

from .models import Payment, PaymentMethod


@admin.register(PaymentMethod)
class PaymentMethodAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "business", "is_cash_like", "is_active", "sort_order")
    list_filter = ("is_active", "is_cash_like", "business")
    search_fields = ("name", "code", "business__name")
    autocomplete_fields = ("business",)


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("business", "direction", "method", "amount", "customer", "created_at")
    list_filter = ("direction", "business", "method")
    search_fields = ("business__name", "customer__name", "reference", "note")
    autocomplete_fields = ("business", "method", "sale", "customer", "created_by")
    date_hierarchy = "created_at"
