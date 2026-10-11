from django.contrib import admin

from .models import Business, BusinessMembership, BusinessType, BusinessTypeField


class BusinessTypeFieldInline(admin.TabularInline):
    model = BusinessTypeField
    extra = 1
    fields = ("name", "field_type", "required", "options", "sort_order")


@admin.register(BusinessType)
class BusinessTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "sort_order", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name",)
    prepopulated_fields = {"slug": ("name",)}
    inlines = [BusinessTypeFieldInline]


@admin.register(BusinessTypeField)
class BusinessTypeFieldAdmin(admin.ModelAdmin):
    list_display = ("name", "business_type", "field_type", "required", "sort_order")
    list_filter = ("field_type", "required", "business_type")
    search_fields = ("name",)


class BusinessMembershipInline(admin.TabularInline):
    model = BusinessMembership
    extra = 0
    autocomplete_fields = ("user",)


@admin.register(Business)
class BusinessAdmin(admin.ModelAdmin):
    list_display = ("name", "business_type", "city", "currency", "is_active", "created_at")
    list_filter = ("is_active", "business_type", "currency")
    search_fields = ("name", "phone", "email", "gst_number")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [BusinessMembershipInline]


@admin.register(BusinessMembership)
class BusinessMembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "business", "role", "is_active")
    list_filter = ("role", "is_active")
    search_fields = ("user__email", "business__name")
    autocomplete_fields = ("user", "business")
