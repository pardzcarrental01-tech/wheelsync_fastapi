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
    assert normalize_government_id("Passport", "ab1234567") == "AB1234567"
    assert normalize_government_id("National ID", "123456789012") == "123456789012"
    with pytest.raises(ValueError):
        normalize_government_id("Passport", "A123")
    with pytest.raises(ValueError):
        normalize_government_id("National ID", "1234-5678-9012")


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
