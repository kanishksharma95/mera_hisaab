"""Sales views: POS, checkout, invoice (view / print / PDF / public / WhatsApp)."""
import json
from urllib.parse import quote

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from core.mixins import business_required
from customers.models import Customer
from payments.models import PaymentMethod
from payments.services import ensure_default_methods
from products.models import Product

from .models import Sale
from .services import create_sale


@business_required
def pos(request):
    """The billing screen. Ensures the business has payment methods first."""
    ensure_default_methods(request.business)
    context = {
        "payment_methods": PaymentMethod.objects.for_business(request.business).filter(
            is_active=True
        ),
        "customers": Customer.objects.for_business(request.business).filter(
            is_active=True
        ).order_by("name"),
        "currency_symbol": request.business.currency_symbol,
    }
    return render(request, "sales/pos.html", context)


@business_required
@require_GET
def pos_search(request):
    """JSON product search for the POS (name / SKU / barcode)."""
    q = request.GET.get("q", "").strip()
    products = Product.objects.for_business(request.business).filter(is_active=True)
    if q:
        products = products.filter(
            Q(name__icontains=q) | Q(sku__icontains=q) | Q(barcode__icontains=q)
        )
    products = products.order_by("name")[:24]
    data = [
        {
            "id": p.id,
            "name": p.name,
            "price": str(p.selling_price),
            "tax": str(p.tax_percent),
            "unit": p.unit,
            "stock": str(p.current_stock),
            "sku": p.sku,
        }
        for p in products
    ]
    return JsonResponse({"results": data})


@business_required
@require_POST
def pos_checkout(request):
    """Create a sale from the POS cart (JSON body). All maths server-side."""
    from payments.limits import can_create_sale

    allowed, limit_msg = can_create_sale(request.business)
    if not allowed:
        return JsonResponse({"error": limit_msg}, status=403)

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"error": "Invalid request."}, status=400)


    raw_items = payload.get("items") or []
    items = [
        {
            "product": it.get("product"),
            "quantity": it.get("quantity"),
            "unit_price": it.get("unit_price"),
            "discount": it.get("discount", 0),
        }
        for it in raw_items
    ]
    payments = [
        {"method": p.get("method"), "amount": p.get("amount")}
        for p in (payload.get("payments") or [])
    ]

    customer = None
    customer_id = payload.get("customer")
    if customer_id:
        customer = Customer.objects.for_business(request.business).filter(
            pk=customer_id
        ).first()
        if customer is None:
            return JsonResponse({"error": "Invalid customer."}, status=400)

    try:
        sale = create_sale(
            business=request.business,
            user=request.user,
            items=items,
            customer=customer,
            order_discount=payload.get("order_discount", 0) or 0,
            payments=payments,
            notes=payload.get("notes", "") or "",
        )
    except ValidationError as exc:
        return JsonResponse({"error": "; ".join(exc.messages)}, status=400)
    except (TypeError, ValueError, KeyError):
        return JsonResponse({"error": "Could not process the sale. Please check the cart."},
                            status=400)

    return JsonResponse({
        "ok": True,
        "invoice_number": sale.invoice_number,
        "redirect": reverse("sales:invoice", args=[sale.pk]),
    })


@business_required
def sale_list(request):
    sales = Sale.objects.for_business(request.business).select_related("customer")
    q = request.GET.get("q", "").strip()
    if q:
        sales = sales.filter(
            Q(invoice_number__icontains=q) | Q(customer__name__icontains=q)
        )
    status = request.GET.get("status")
    if status in {"paid", "partial", "unpaid"}:
        sales = sales.filter(payment_status=status)

    sales = sales.order_by("-created_at")
    paginator = Paginator(sales, 25)
    page_obj = paginator.get_page(request.GET.get("page"))
    querystring = request.GET.copy()
    querystring.pop("page", None)
    return render(request, "sales/sale_list.html", {
        "page_obj": page_obj, "q": q, "status": status,
        "querystring": querystring.urlencode(),
    })


def _sale_with_items(business, pk):
    return get_object_or_404(
        Sale.objects.select_related("customer", "business").prefetch_related("items", "payments__method"),
        pk=pk, business=business,
    )


@business_required
def invoice(request, pk):
    sale = _sale_with_items(request.business, pk)
    return render(request, "sales/invoice.html", {
        "sale": sale, "business": sale.business, "public": False,
        "whatsapp_url": _whatsapp_url(request, sale),
    })


@business_required
def invoice_pdf(request, pk):
    sale = _sale_with_items(request.business, pk)
    return _render_pdf(request, sale)


@business_required
def invoice_thermal(request, pk):
    """Compact 58mm/80mm thermal receipt layout for POS printers."""
    sale = _sale_with_items(request.business, pk)
    return render(request, "sales/thermal.html", {
        "sale": sale,
        "business": sale.business,
    })



def public_invoice(request, token):
    """Read-only invoice page reachable by anyone with the link (WhatsApp)."""
    sale = get_object_or_404(
        Sale.objects.select_related("customer", "business").prefetch_related("items"),
        public_token=token,
    )
    from payments import gateway

    return render(request, "sales/invoice.html", {
        "sale": sale, "business": sale.business, "public": True,
        "razorpay_enabled": gateway.is_configured() and sale.due_amount > 0,
    })


def _render_pdf(request, sale):
    from xhtml2pdf import pisa

    # The default PDF font has no ₹ glyph; use a safe label for INR.
    pdf_symbol = "Rs. " if sale.business.currency == "INR" else sale.business.currency_symbol
    html = render(request, "sales/invoice_pdf.html", {
        "sale": sale, "business": sale.business, "sym": pdf_symbol,
    }).content.decode("utf-8")
    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{sale.invoice_number}.pdf"'
    result = pisa.CreatePDF(src=html, dest=response, encoding="utf-8")
    if result.err:
        return HttpResponse("Could not generate PDF.", status=500)
    return response


def _whatsapp_url(request, sale):
    """Build a wa.me share link with an invoice summary + public link."""
    public_link = request.build_absolute_uri(
        reverse("public_invoice", args=[sale.public_token])
    )
    sym = sale.business.currency_symbol
    lines = [
        f"Namaste{(' ' + sale.customer.name) if sale.customer else ''},",
        f"Invoice {sale.invoice_number} — {sale.business.name}",
        f"Total: {sym}{sale.total}",
    ]
    if sale.due_amount > 0:
        lines.append(f"Pending udhaar: {sym}{sale.due_amount}")
    lines.append(f"View: {public_link}")
    lines.append("")
    lines.append("Powered by Mera Hisaab")
    text = quote("\n".join(lines))

    phone = ""
    if sale.customer and sale.customer.phone:
        digits = "".join(ch for ch in sale.customer.phone if ch.isdigit())
        if len(digits) == 10:
            digits = "91" + digits
        phone = digits
    return f"https://wa.me/{phone}?text={text}"


@business_required
def sale_export_csv(request):
    """Export sales records to CSV."""
    import csv

    sales = (
        Sale.objects.for_business(request.business)
        .select_related("customer")
        .order_by("-created_at")
    )
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="sales_export.csv"'
    writer = csv.writer(response)
    writer.writerow([
        "Invoice Number",
        "Date",
        "Customer",
        "Subtotal",
        "Discount",
        "Tax",
        "Total",
        "Paid",
        "Due",
        "Status",
    ])
    for s in sales:
        writer.writerow([
            s.invoice_number,
            s.created_at.strftime("%Y-%m-%d %H:%M"),
            s.customer.name if s.customer else "Walk-in",
            s.subtotal,
            s.discount_total,
            s.tax_total,
            s.total,
            s.paid_amount,
            s.due_amount,
            s.payment_status,
        ])
    return response

