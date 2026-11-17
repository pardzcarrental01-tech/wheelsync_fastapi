import uuid
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..deps import get_current_user, get_optional_current_user, parse_uuid, require_admin
from ..models import Booking, BookingStatus, Profile, UserRole, Vehicle, VehicleStatus, WalkInTransaction
from ..realtime import hub
from ..schemas import (
    UnavailableDateOut, VehicleAdminOut, VehicleCreate, VehicleCustomerOut, VehicleUpdate,
)
from ..services import audit, storage
from ..services.bookings import booking_interval, today_local
from ..services.synthetic import is_real_vehicle

router = APIRouter(prefix="/vehicles", tags=["vehicles"])
PLATE_TAKEN = "A vehicle with this plate number already exists."


def _label(vehicle: Vehicle) -> str:
    return f"{vehicle.year} {vehicle.name} ({vehicle.plate_number})" if vehicle.year else f"{vehicle.name} ({vehicle.plate_number})"


def _plain(value):
    """Enum members as their value, so the audit line reads 'maintenance', not 'VehicleStatus.maintenance'."""
    return getattr(value, "value", value)


@router.get("")
def list_vehicles(user: Profile | None = Depends(get_optional_current_user), db: Session = Depends(get_db)):
    """Public visitors and customers see every car except those under maintenance or cleaning, without pricing; admins see
    the full fleet. A rented car stays listed: only its booked dates are blocked (see /unavailable-dates).
    Synthetic test vehicles are left out for everyone (see services/synthetic.py)."""
    if user is not None and user.role == UserRole.admin:
        rows = db.scalars(select(Vehicle).where(is_real_vehicle()).order_by(Vehicle.created_at.desc())).all()
        return [VehicleAdminOut.model_validate(v) for v in rows]
    rows = db.scalars(
        select(Vehicle).where(
            Vehicle.status.not_in((VehicleStatus.maintenance, VehicleStatus.cleaning)),
            is_real_vehicle(),
        ).order_by(Vehicle.make, Vehicle.model)
    ).all()
    return [VehicleCustomerOut.model_validate(v) for v in rows]


@router.get("/unavailable-dates", response_model=list[UnavailableDateOut])
def unavailable_dates(_: Profile = Depends(get_current_user), db: Session = Depends(get_db)):
    """Occupied local-time intervals only (no booking details) for customer availability checks."""
    now = datetime.now(ZoneInfo(get_settings().timezone)).replace(tzinfo=None)
    rows = db.scalars(
        select(Booking)
        .where(
            or_(
                Booking.status.in_((BookingStatus.accepted, BookingStatus.ongoing)),
                (Booking.status == BookingStatus.completed) & (
                    Booking.released_at.is_(None)
                    | (Booking.end_date >= today_local() - timedelta(days=1))
                ),
            )
        )
    ).all()
    recorded = db.execute(
        select(WalkInTransaction.vehicle_id, WalkInTransaction.start_date, WalkInTransaction.end_date)
        .where(WalkInTransaction.vehicle_id.is_not(None), WalkInTransaction.end_date >= today_local())
    ).all()
    occupied = []
    for booking in rows:
        starts_at, ends_at = booking_interval(booking)
        if ends_at > now:
            occupied.append(UnavailableDateOut(
                vehicle_id=booking.vehicle_id,
                start_date=starts_at.date(),
                end_date=(ends_at - timedelta(microseconds=1)).date(),
                start_at=starts_at,
                end_at=ends_at,
            ))
    for transaction in recorded:
        starts_at = datetime.combine(transaction.start_date, time.min)
        ends_at = datetime.combine(transaction.end_date + timedelta(days=1), time.min)
        if ends_at > now:
            occupied.append(UnavailableDateOut(
                vehicle_id=transaction.vehicle_id,
                start_date=transaction.start_date,
                end_date=transaction.end_date,
                start_at=starts_at,
                end_at=ends_at,
            ))
    return occupied


@router.post("/images", dependencies=[Depends(require_admin)])
def upload_vehicle_image(file: UploadFile = File(...)):
    relative = storage.save_photo(storage.VEHICLE_BUCKET, file)
    base = get_settings().public_base_url.rstrip("/")
    return {"image_url": f"{base}/files/{storage.VEHICLE_BUCKET}/{relative}"}


@router.post("", response_model=VehicleAdminOut, status_code=status.HTTP_201_CREATED)
def create_vehicle(data: VehicleCreate, admin: Profile = Depends(require_admin), db: Session = Depends(get_db)):
    vehicle = Vehicle(**data.model_dump())
    vehicle.plate_number = vehicle.plate_number.strip()
    db.add(vehicle)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, PLATE_TAKEN)
    hub.publish("bookings")
    audit.record(db, admin, "vehicle.create", f"Added vehicle {_label(vehicle)}", entity="vehicle", entity_id=vehicle.id)
    return vehicle


@router.patch("/{vehicle_id}", response_model=VehicleAdminOut)
def update_vehicle(vehicle_id: str, data: VehicleUpdate, admin: Profile = Depends(require_admin), db: Session = Depends(get_db)):
    vehicle = db.get(Vehicle, parse_uuid(vehicle_id, "Vehicle"))
    if vehicle is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Vehicle not found")
    changes = data.model_dump(exclude_unset=True)
    if "image_url" in changes and changes["image_url"] in ("", None):
        changes["image_url"] = None
    changed = []
    for key, value in changes.items():
        value = value.strip() if key == "plate_number" else value
        old, new = _plain(getattr(vehicle, key)), _plain(value)
        if str(old) != str(new):
            changed.append(f"{key}: {old} -> {new}")
        setattr(vehicle, key, value)
    if "status" in changes:
        vehicle.auto_rented = False  # the admin picked the status by hand
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, PLATE_TAKEN)
    hub.publish("bookings")
    if changed:
        audit.record(db, admin, "vehicle.update", f"Updated {_label(vehicle)}: " + "; ".join(changed), entity="vehicle", entity_id=vehicle.id)
    return vehicle


@router.delete("/{vehicle_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_vehicle(vehicle_id: str, admin: Profile = Depends(require_admin), db: Session = Depends(get_db)):
    vid: uuid.UUID = parse_uuid(vehicle_id, "Vehicle")
    vehicle = db.get(Vehicle, vid)
    if vehicle is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Vehicle not found")
    if db.scalar(select(func.count()).select_from(Booking).where(Booking.vehicle_id == vid)):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This vehicle has booking records and cannot be deleted. Set it to Maintenance instead.",
        )
    label = _label(vehicle)
    db.delete(vehicle)
    db.commit()
    hub.publish("bookings")
    audit.record(db, admin, "vehicle.delete", f"Deleted vehicle {label}", entity="vehicle", entity_id=vid)
