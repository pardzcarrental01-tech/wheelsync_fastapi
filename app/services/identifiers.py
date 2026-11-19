import re

# Driver's License (LTO): one letter, 2 digits, dash, 2 digits, dash, 6 digits, e.g. A12-34-567890
_LTO = re.compile(r"[A-Z]\d{2}-\d{2}-\d{6}")
_OTHER = re.compile(r"[A-Za-z0-9-]{4,20}")
_DRIVERS_LICENSE_TYPES = {"driver's license", "driver’s license", "drivers license", "driver license"}
_PHILSYS_TYPES = {"national id", "philippine national id", "philsys id"}


def normalize_government_id(id_type: str | None, number: str | None) -> str:
    """Check the number against the ID type it belongs to and return the stored form."""
    value = (number or "").strip()
    kind = (id_type or "").strip().casefold()
    if kind in _DRIVERS_LICENSE_TYPES:
        cleaned = re.sub(r"[^A-Za-z0-9]", "", value).upper()[:11]
        out = cleaned[:3]
        if len(cleaned) > 3:
            out += "-" + cleaned[3:5]
        if len(cleaned) > 5:
            out += "-" + cleaned[5:11]
        if not _LTO.fullmatch(out):
            raise ValueError("Driver's license number must follow the LTO format, for example A12-34-567890.")
        return out
    if kind == "passport":
        if not re.fullmatch(r"[A-Za-z0-9]{9}", value):
            raise ValueError("Passport number must be exactly 9 letters or digits.")
        return value.upper()
    if kind in _PHILSYS_TYPES:
        if not re.fullmatch(r"\d{12}", value):
            raise ValueError("PhilSys National ID number must be exactly 12 digits.")
        return value
    if not _OTHER.fullmatch(value):
        raise ValueError("This ID number must be 4 to 20 letters, digits, or dashes.")
    return value
