"""Normalize Philippine mobile numbers to the domestic 11-digit 09XXXXXXXXX form."""
import re

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Profile, UserRole


def normalize_ph_mobile(phone: str | None) -> str | None:
    if phone is None or not phone.strip():
        return None
    value = phone.strip()
    if not re.fullmatch(r"\+?[\d\s().-]+", value):
        raise ValueError("Enter a valid Philippine mobile number.")
    digits = "".join(ch for ch in value if ch.isdigit())
    if digits.startswith("63") and len(digits) == 12:
        digits = "0" + digits[2:]
    elif digits.startswith("9") and len(digits) == 10:
        digits = "0" + digits
    if len(digits) != 11 or not digits.startswith("09"):
        raise ValueError("Enter 10 digits after +63 (or 11 digits starting with 09).")
    return digits


def phone_digits(phone: str | None) -> str:
    try:
        return normalize_ph_mobile(phone) or ""
    except ValueError:
        return "".join(ch for ch in phone or "" if ch.isdigit())


def find_staff_by_phone(db: Session, phone: str) -> Profile | None:
    digits = phone_digits(phone)
    if len(digits) < 7:
        return None
    staff = db.scalars(select(Profile).where(Profile.role == UserRole.staff, func.coalesce(Profile.phone, "") != "")).all()
    return next((member for member in staff if phone_digits(member.phone) == digits), None)
