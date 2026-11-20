from datetime import date, datetime, time, timezone
from types import SimpleNamespace

import pytest

from app.models import BookingStatus
from app.services.bookings import _intervals_overlap, booking_interval
from app.services.identifiers import normalize_government_id
from app.services.phones import normalize_ph_mobile


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("+63 917 123 4567", "09171234567"),
        ("0917-123-4567", "09171234567"),
        ("9171234567", "09171234567"),
    ],
)
def test_philippine_mobile_numbers_are_normalized(value, expected):
    assert normalize_ph_mobile(value) == expected


def test_phone_and_government_id_lengths_are_enforced():
    with pytest.raises(ValueError):
        normalize_ph_mobile("+63 917 123 456")
    assert normalize_government_id("Passport", "p1234567a") == "P1234567A"
    assert normalize_government_id("Passport", "eb1234567") == "EB1234567"
    # National ID: the 16-digit PhilSys Card Number (PCN), stored as printed on the card
    assert normalize_government_id("National ID", "1234567890123456") == "1234-5678-9012-3456"
    assert normalize_government_id("UMID", "011112345678") == "0111-1234567-8"
    assert normalize_government_id("SSS ID", "3412345678") == "34-1234567-8"
    assert normalize_government_id("TIN ID", "123456789") == "123-456-789"
    assert normalize_government_id("TIN ID", "123456789000") == "123-456-789-000"
    assert normalize_government_id("PhilHealth ID", "123456789012") == "12-345678901-2"
    assert normalize_government_id("Pag-IBIG ID", "123456789012") == "1234-5678-9012"
    assert normalize_government_id("PRC ID", "0123456") == "0123456"
    for id_type, bad in [
        ("Passport", "A123"),
        ("National ID", "123456789012"),  # the 12-digit PSN is not accepted
        ("UMID", "12345"),
        ("SSS ID", "12345678901"),
        ("TIN ID", "1234567890"),
        ("PRC ID", "12345678"),
    ]:
        with pytest.raises(ValueError):
            normalize_government_id(id_type, bad)


def test_return_date_opens_at_cleaning_and_verification_time():
    booking = SimpleNamespace(
        status=BookingStatus.completed,
        start_date=date(2026, 11, 16),
        end_date=date(2026, 11, 17),
        pickup_time=time(9, 0),
        released_at=datetime(2026, 11, 17, 4, 0, tzinfo=timezone.utc),
    )
    starts_at, ends_at = booking_interval(booking)
    assert ends_at == datetime(2026, 11, 17, 12, 0)
    assert _intervals_overlap(
        (datetime(2026, 11, 17, 11, 59), datetime(2026, 11, 18)),
        (starts_at, ends_at),
    )
    assert not _intervals_overlap(
        (datetime(2026, 11, 17, 12, 0), datetime(2026, 11, 18)),
        (starts_at, ends_at),
    )


def test_unreleased_rental_stays_blocked_until_cleaning_and_verification_finish():
    booking = SimpleNamespace(
        status=BookingStatus.completed,
        start_date=date(2026, 11, 16),
        end_date=date(2026, 11, 17),
        pickup_time=time(9, 0),
        released_at=None,
    )
    assert booking_interval(booking)[1] == datetime.max


def test_active_rental_only_blocks_until_its_return_time():
    booking = SimpleNamespace(
        status=BookingStatus.accepted,
        start_date=date(2026, 11, 19),
        end_date=date(2026, 11, 20),
        pickup_time=time(9, 0),
        return_time=time(15, 0),
        released_at=None,
    )
    starts_at, ends_at = booking_interval(booking)
    assert ends_at == datetime(2026, 11, 20, 15, 0)
    # Someone else can still take the car for the rest of the return day.
    assert not _intervals_overlap((datetime(2026, 11, 20, 15, 0), datetime(2026, 11, 20, 21, 0)), (starts_at, ends_at))
    assert _intervals_overlap((datetime(2026, 11, 20, 9, 0), datetime(2026, 11, 20, 21, 0)), (starts_at, ends_at))
