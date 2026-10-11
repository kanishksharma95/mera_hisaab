from django.contrib import admin

from .models import Customer, CustomerLedgerEntry


class CustomerLedgerEntryInline(admin.TabularInline):
    model = CustomerLedgerEntry
    extra = 0
    fields = ("created_at", "entry_type", "amount", "balance_after", "description", "method")
    readonly_fields = ("created_at", "balance_after")
    ordering = ("-created_at",)


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("name", "business", "phone", "current_balance", "is_active")
    list_filter = ("is_active", "business")
    search_fields = ("name", "phone", "email", "business__name")
    autocomplete_fields = ("business",)
    readonly_fields = ("current_balance",)  # changes only via ledger services
    inlines = [CustomerLedgerEntryInline]


@admin.register(CustomerLedgerEntry)
class CustomerLedgerEntryAdmin(admin.ModelAdmin):
    list_display = ("customer", "business", "entry_type", "amount", "balance_after", "created_at")
    list_filter = ("entry_type", "business")
    search_fields = ("customer__name", "business__name", "description", "reference")
    autocomplete_fields = ("business", "customer", "created_by")
    readonly_fields = ("balance_after",)
    date_hierarchy = "created_at"
