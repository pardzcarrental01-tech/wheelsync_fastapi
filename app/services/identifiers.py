import re


def normalize_government_id(id_type: str | None, number: str | None) -> str:
    value = (number or "").strip()
    kind = (id_type or "").strip().casefold()
    if kind == "passport":
        if not re.fullmatch(r"[A-Za-z0-9]{9}", value):
            raise ValueError("Passport number must be exactly 9 letters or digits.")
        return value.upper()
    if kind in {"national id", "philippine national id", "philsys id"}:
        if not re.fullmatch(r"\d{12}", value):
            raise ValueError("PhilSys National ID number must be exactly 12 digits.")
    return value
