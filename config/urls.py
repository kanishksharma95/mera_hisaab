"""
Root URL configuration for Mera Hisaab.

Django Admin is rebranded as the internal 'Mera Hisaab Admin' (Super Admin).
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from core import views as core_views
from customers import views as customer_views
from sales import views as sales_views

# --- Super Admin branding ---
admin.site.site_header = "Mera Hisaab Admin"
admin.site.site_title = "Mera Hisaab Admin"
admin.site.index_title = "Platform administration"

urlpatterns = [
    path("healthz/", core_views.healthz, name="healthz"),
    path("admin/", admin.site.urls),
    path("accounts/", include("accounts.urls")),
    path("products/", include("products.urls")),
    path("inventory/", include("inventory.urls")),
    path("customers/", include("customers.urls")),
    path("udhaar/", customer_views.udhaar_dashboard, name="udhaar"),
    path("sales/", include("sales.urls")),
    path("suppliers/", include("suppliers.urls")),
    path("purchases/", include("purchases.urls")),
    path("payments/", include("payments.urls")),
    path("expenses/", include("expenses.urls")),
    # Public, tokenised invoice page (no auth) — used for WhatsApp sharing.
    path("i/<uuid:token>/", sales_views.public_invoice, name="public_invoice"),
    path("", include("businesses.urls")),
    path("", include("core.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.BASE_DIR / "static")
