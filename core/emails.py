"""
SaaS Platform Email Service (Tareeqa A).

Sends emails on behalf of any shop / tenant without requiring individual
shopkeepers to configure SMTP or enter their personal email passwords.

Design:
1. Physical Delivery: Dispatched through the platform's central SMTP
   (e.g. Gmail / Brevo / SendGrid configured in settings).
2. Tenant Branding:
   From header is formatted as:
       `"{business.name} (via Mera Hisaab)" <{central_sender}>`
3. Direct Reply-To:
   The Reply-To header is set to the shopkeeper's email (business.email
   or owner's email). When a customer replies to an invoice or reminder,
   the reply arrives directly in the shopkeeper's personal mailbox!
"""
from email.utils import formataddr
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags


def get_business_reply_to_email(business):
    """Resolve the best reply-to email for a tenant business."""
    if business and business.email:
        return business.email.strip()

    # Fallback to business owner's email from membership
    if business:
        from businesses.models import BusinessMembership
        owner_membership = (
            BusinessMembership.objects.filter(
                business=business, role=BusinessMembership.Role.OWNER
            )
            .select_related("user")
            .first()
        )
        if owner_membership and owner_membership.user.email:
            return owner_membership.user.email.strip()

    return ""


def send_tenant_branded_email(
    business,
    subject,
    recipient_list,
    template_name=None,
    context=None,
    plain_body=None,
    reply_to=None,
):
    """
    Send an email with tenant branding (Tareeqa A).

    :param business: Business tenant instance
    :param subject: Email subject string
    :param recipient_list: List of recipient email strings
    :param template_name: HTML template path (optional)
    :param context: Template context dict (optional)
    :param plain_body: Plain text fallback body (optional)
    :param reply_to: Custom reply-to email (optional, defaults to business owner)
    :return: int count of sent emails
    """
    if not recipient_list:
        return 0

    if isinstance(recipient_list, str):
        recipient_list = [recipient_list]

    ctx = context.copy() if context else {}
    if business:
        ctx.setdefault("business", business)
    ctx.setdefault("APP_NAME", getattr(settings, "APP_NAME", "Mera Hisaab"))

    # Render HTML if template provided
    html_content = None
    if template_name:
        html_content = render_to_string(template_name, ctx)
        text_content = plain_body or strip_tags(html_content)
    else:
        text_content = plain_body or subject

    # Central authenticated email address
    central_sender = getattr(settings, "EMAIL_HOST_USER", "") or getattr(
        settings, "DEFAULT_FROM_EMAIL", "no-reply@merahisaab.app"
    )
    # Extract raw email if it's in "Name <email@xyz>" format
    if "<" in central_sender and ">" in central_sender:
        central_sender = central_sender.split("<")[1].split(">")[0].strip()

    # Friendly sender display name: "Sharma Kirana Store (via Mera Hisaab)"
    shop_display_name = (
        f"{business.name} (via Mera Hisaab)" if business and business.name else "Mera Hisaab"
    )
    from_email = formataddr((shop_display_name, central_sender))

    # Resolve Reply-To
    target_reply_to = reply_to or get_business_reply_to_email(business)
    reply_to_list = [target_reply_to] if target_reply_to else None

    email = EmailMultiAlternatives(
        subject=subject,
        body=text_content,
        from_email=from_email,
        to=recipient_list,
        reply_to=reply_to_list,
    )

    if html_content:
        email.attach_alternative(html_content, "text/html")

    return email.send(fail_silently=False)
