"""ID number rules for the Philippine IDs accepted by Pardz Car Rental (same rules as lib/identifiers.js
in the customer website and the admin console). The number is stored in the grouping printed on the card.

  Driver's License (LTO)  1 letter + 10 digits                       A12-34-567890
  Passport (DFA)          1-2 letters + 6-7 digits (+ 1 letter)      P1234567A
  National ID (PhilSys)   16-digit PhilSys Card Number (PCN)         1234-5678-9012-3456
                          (not the 12-digit PSN, which the PSA asks businesses not to collect)
  UMID                    12-digit Common Reference Number (CRN)     0111-1234567-8
  SSS ID                  10 digits                                  34-1234567-8
  TIN ID                  9 digits, or 12 with the branch code       123-456-789 / 123-456-789-000
  PhilHealth ID           12-digit PIN                               12-345678901-2
  Pag-IBIG ID             12-digit MID                               1234-5678-9012
  PRC ID                  7-digit registration number                0123456
  Others                  4 to 20 letters, digits or dashes
"""
import re

_LTO = re.compile(r"[A-Z]\d{2}-\d{2}-\d{6}")
_PASSPORT = re.compile(r"[A-Z]{1,2}\d{6,7}[A-Z]?")
_OTHER = re.compile(r"[A-Za-z0-9-]{4,20}")

_NAMES = {
    "drivers_license": {"driver's license", "driver’s license", "drivers license", "driver license"},
    "passport": {"passport"},
    "philsys": {"national id", "philippine national id", "philsys id", "philid"},
    "umid": {"umid", "umid id", "unified multi-purpose id"},
    "sss": {"sss id", "sss"},
    "tin": {"tin id", "tin"},
    "philhealth": {"philhealth id", "philhealth"},
    "pagibig": {"pag-ibig id", "pag-ibig", "pagibig id", "pagibig"},
    "prc": {"prc id", "prc"},
}

# kind: (digit groups, last group optional, label, example)
_DIGIT_RULES = {
    "philsys": ((4, 4, 4, 4), False, "National ID number must be the 16-digit PhilSys Card Number (PCN)", "1234-5678-9012-3456"),
    "umid": ((4, 7, 1), False, "UMID number must be the 12-digit Common Reference Number (CRN)", "0111-1234567-8"),
    "sss": ((2, 7, 1), False, "SSS number must be 10 digits", "34-1234567-8"),
    "tin": ((3, 3, 3, 3), True, "TIN must be 9 digits, or 12 digits with the branch code", "123-456-789-000"),
    "philhealth": ((2, 9, 1), False, "PhilHealth number (PIN) must be 12 digits", "12-345678901-2"),
    "pagibig": ((4, 4, 4), False, "Pag-IBIG MID number must be 12 digits", "1234-5678-9012"),
    "prc": ((7,), False, "PRC registration number must be 7 digits", "0123456"),
}


def _kind(id_type: str | None) -> str:
    value = (id_type or "").strip().casefold()
    return next((kind for kind, names in _NAMES.items() if value in names), "other")


def _group(digits: str, groups: tuple[int, ...]) -> str:
    parts, start = [], 0
    for size in groups:
        if start >= len(digits):
            break
        parts.append(digits[start:start + size])
        start += size
    return "-".join(parts)


def normalize_government_id(id_type: str | None, number: str | None) -> str:
    """Check the number against the ID type it belongs to and return the stored form."""
    value = (number or "").strip()
    kind = _kind(id_type)
    if kind == "drivers_license":
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
        cleaned = re.sub(r"[^A-Za-z0-9]", "", value).upper()
        if not _PASSPORT.fullmatch(cleaned):
            raise ValueError("Passport number must be 7 to 9 letters and digits as printed, for example P1234567A.")
        return cleaned
    if kind in _DIGIT_RULES:
        groups, optional_last, label, example = _DIGIT_RULES[kind]
        digits = re.sub(r"\D", "", value)
        allowed = {sum(groups)} | ({sum(groups[:-1])} if optional_last else set())
        if len(digits) not in allowed or len(digits) != len(re.sub(r"[\s-]", "", value)):
            raise ValueError(f"{label}, for example {example}.")
        return _group(digits, groups)
    if not _OTHER.fullmatch(value):
        raise ValueError("This ID number must be 4 to 20 letters, digits, or dashes.")
    return value
