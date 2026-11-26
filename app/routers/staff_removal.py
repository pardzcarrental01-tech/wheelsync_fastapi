from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import parse_uuid, require_admin
from ..models import Booking, Inspection, Profile, TransactionExtension, UserRole, WalkInTransaction
from ..services import audit

router = APIRouter(prefix="/admin/staff", tags=["admin"], dependencies=[Depends(require_admin)])


@router.delete("/{staff_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_staff(staff_id: str, admin: Profile = Depends(require_admin), db: Session = Depends(get_db)):
    """Remove a staff account. Refused when the account is part of any booking, inspection or payment record,
    because those records must keep their history."""
    staff = db.get(Profile, parse_uuid(staff_id, "Staff member"))
    if staff is None or staff.role != UserRole.staff:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Staff member not found")

    has_history = (
        db.scalar(select(Booking.id).where(or_(
            Booking.assigned_staff_id == staff.id,
            Booking.cleaning_staff_id == staff.id,
            Booking.decided_by == staff.id,
        )).limit(1))
        or db.scalar(select(Inspection.id).where(or_(
            Inspection.staff_id == staff.id,
            Inspection.verified_by == staff.id,
        )).limit(1))
        or db.scalar(select(Profile.id).where(or_(
            Profile.verified_by == staff.id,
            Profile.created_by == staff.id,
        )).limit(1))
        or db.scalar(select(WalkInTransaction.id).where(WalkInTransaction.created_by == staff.id).limit(1))
        or db.scalar(select(TransactionExtension.id).where(TransactionExtension.created_by == staff.id).limit(1))
    )
    if has_history:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"{staff.full_name} has bookings, inspections or payments on record, so the account can't be removed "
            "without losing that history.",
        )

    name = staff.full_name
    contact = staff.email or staff.phone or "no contact"
    db.delete(staff)
    db.commit()
    audit.record(db, admin, "staff.delete", f"Removed staff account {name} ({contact})", entity="staff", entity_id=staff_id)
