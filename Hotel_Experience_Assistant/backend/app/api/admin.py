import secrets

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.services import admin as admin_service

router = APIRouter(prefix="/api/admin")


class LoginRequest(BaseModel):
    password: str


@router.post("/login")
def login(payload: LoginRequest, request: Request):
    if not settings.admin_password or not secrets.compare_digest(payload.password, settings.admin_password):
        raise HTTPException(status_code=401, detail="invalid password")
    request.session["is_admin"] = True
    return {"authenticated": True}


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return {"authenticated": False}


@router.get("/me")
def me(request: Request):
    return {"authenticated": bool(request.session.get("is_admin"))}


def require_admin(request: Request) -> None:
    if not request.session.get("is_admin"):
        raise HTTPException(status_code=401, detail="not authenticated")


@router.get("/bookings", dependencies=[Depends(require_admin)])
def bookings(db: Session = Depends(get_db)):
    return admin_service.list_bookings(db)


@router.get("/checkins", dependencies=[Depends(require_admin)])
def checkins(db: Session = Depends(get_db)):
    return admin_service.list_checkins(db)


@router.get("/conversations", dependencies=[Depends(require_admin)])
def conversations(db: Session = Depends(get_db)):
    return admin_service.list_conversations(db)


@router.get("/conversations/{conversation_id}", dependencies=[Depends(require_admin)])
def conversation_detail(conversation_id: int, db: Session = Depends(get_db)):
    messages = admin_service.get_conversation_messages(db, conversation_id)
    if messages is None:
        raise HTTPException(status_code=404, detail="conversation not found")
    return messages
