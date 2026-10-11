from django.urls import path

from . import views

app_name = "payments"

urlpatterns = [
    path("", views.payment_list, name="list"),
    path("methods/", views.method_list, name="method_list"),
    path("methods/add/", views.method_create, name="method_add"),
    path("methods/<int:pk>/edit/", views.method_edit, name="method_edit"),
    path("methods/<int:pk>/toggle/", views.method_toggle, name="method_toggle"),

    # Razorpay — customer invoice collection (public endpoints)
    path("invoice/<uuid:token>/order/", views.create_invoice_order, name="invoice_order"),
    path("invoice/<uuid:token>/callback/", views.invoice_payment_callback, name="invoice_callback"),
    # Razorpay — webhook (source of truth; unauthenticated but signature-verified)
    path("webhook/razorpay/", views.razorpay_webhook, name="razorpay_webhook"),

    # SaaS subscription billing (shopkeeper-facing)
    path("billing/", views.billing, name="billing"),
    path("billing/subscribe/", views.create_subscription_view, name="subscribe"),
]
