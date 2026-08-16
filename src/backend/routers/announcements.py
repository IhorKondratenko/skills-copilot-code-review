"""
Announcement endpoints for the High School Management System API
"""

import uuid
from datetime import date
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from ..database import announcements_collection, teachers_collection

router = APIRouter(
    prefix="/announcements",
    tags=["announcements"]
)


class AnnouncementInput(BaseModel):
    message: str = Field(..., min_length=1, max_length=500)
    start_date: Optional[str] = None
    expiration_date: str

    @field_validator("message")
    @classmethod
    def strip_message(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Message cannot be empty")
        return stripped

    @field_validator("start_date", "expiration_date")
    @classmethod
    def validate_date_format(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        try:
            date.fromisoformat(value)
        except ValueError:
            raise ValueError("Dates must be in YYYY-MM-DD format")
        return value


def _require_teacher(teacher_username: Optional[str]) -> Dict[str, Any]:
    """Ensure the request is made by an authenticated teacher/admin"""
    if not teacher_username:
        raise HTTPException(
            status_code=401, detail="Authentication required for this action")

    teacher = teachers_collection.find_one({"_id": teacher_username})
    if not teacher:
        raise HTTPException(
            status_code=401, detail="Invalid teacher credentials")

    return teacher


def _serialize(announcement: Dict[str, Any]) -> Dict[str, Any]:
    result = dict(announcement)
    result["id"] = result.pop("_id")
    return result


@router.get("/active", response_model=List[Dict[str, Any]])
def get_active_announcements() -> List[Dict[str, Any]]:
    """Get all currently active announcements - public endpoint for the banner"""
    today = date.today().isoformat()

    query = {
        "expiration_date": {"$gte": today},
        "$or": [
            {"start_date": None},
            {"start_date": {"$exists": False}},
            {"start_date": {"$lte": today}},
        ],
    }

    announcements = announcements_collection.find(
        query).sort("expiration_date", 1)
    return [_serialize(a) for a in announcements]


@router.get("", response_model=List[Dict[str, Any]])
@router.get("/", response_model=List[Dict[str, Any]])
def get_all_announcements(teacher_username: Optional[str] = Query(None)) -> List[Dict[str, Any]]:
    """Get all announcements for management - requires teacher authentication"""
    _require_teacher(teacher_username)

    announcements = announcements_collection.find().sort("expiration_date", 1)
    return [_serialize(a) for a in announcements]


@router.post("", response_model=Dict[str, Any])
@router.post("/", response_model=Dict[str, Any])
def create_announcement(payload: AnnouncementInput, teacher_username: Optional[str] = Query(None)) -> Dict[str, Any]:
    """Create a new announcement - requires teacher authentication"""
    teacher = _require_teacher(teacher_username)

    if payload.start_date and payload.start_date > payload.expiration_date:
        raise HTTPException(
            status_code=400, detail="Start date must be before expiration date")

    announcement = {
        "_id": str(uuid.uuid4()),
        "message": payload.message,
        "start_date": payload.start_date,
        "expiration_date": payload.expiration_date,
        "created_by": teacher["username"],
    }

    announcements_collection.insert_one(announcement)
    return _serialize(announcement)


@router.put("/{announcement_id}", response_model=Dict[str, Any])
def update_announcement(
    announcement_id: str,
    payload: AnnouncementInput,
    teacher_username: Optional[str] = Query(None),
) -> Dict[str, Any]:
    """Update an existing announcement - requires teacher authentication"""
    _require_teacher(teacher_username)

    if payload.start_date and payload.start_date > payload.expiration_date:
        raise HTTPException(
            status_code=400, detail="Start date must be before expiration date")

    existing = announcements_collection.find_one({"_id": announcement_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Announcement not found")

    updates = {
        "message": payload.message,
        "start_date": payload.start_date,
        "expiration_date": payload.expiration_date,
    }
    announcements_collection.update_one(
        {"_id": announcement_id}, {"$set": updates})

    updated = announcements_collection.find_one({"_id": announcement_id})
    return _serialize(updated)


@router.delete("/{announcement_id}")
def delete_announcement(announcement_id: str, teacher_username: Optional[str] = Query(None)) -> Dict[str, str]:
    """Delete an announcement - requires teacher authentication"""
    _require_teacher(teacher_username)

    result = announcements_collection.delete_one({"_id": announcement_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Announcement not found")

    return {"message": "Announcement deleted"}
