"""Reusable field validators shared across apps."""
import re

from django.core.exceptions import ValidationError


def validate_phone(value):
    """Lenient phone check: 7–15 digits once separators are stripped.

    Accepts spaces, +, -, (), etc. around the digits so real-world formats
    (+91 98765 43210, (022) 1234-5678) pass, while a bare "abc" or a stray
    number of the wrong length is rejected. Blank is allowed by the caller
    (the field's ``required``), so empty input is treated as "no phone".
    """
    if value in (None, ""):
        return
    digits = re.sub(r"\D", "", str(value))
    if not (7 <= len(digits) <= 15):
        raise ValidationError(
            "Enter a valid phone number (7–15 digits)."
        )
