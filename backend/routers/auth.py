import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from auth import create_token, hash_password, require_user, verify_password
from database import get_db
from models import User, UserMeasurements

router = APIRouter()


# ------------------------------------------------------------------
# Request / response models
# ------------------------------------------------------------------

class RegisterRequest(BaseModel):
    email:    EmailStr
    password: str = Field(..., min_length=6)


class AuthResponse(BaseModel):
    access_token: str
    token_type:   str = "bearer"
    email:        str


class MeasurementsPayload(BaseModel):
    data: dict


# ------------------------------------------------------------------
# Auth routes
# ------------------------------------------------------------------

@router.post("/auth/register", response_model=AuthResponse)
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == req.email).first():
        raise HTTPException(status_code=409, detail="Email already registered.")
    user = User(email=req.email, hashed_password=hash_password(req.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return AuthResponse(access_token=create_token(user.id), email=user.email)


@router.post("/auth/login", response_model=AuthResponse)
def login(req: RegisterRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == req.email).first()
    if not user or not verify_password(req.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    return AuthResponse(access_token=create_token(user.id), email=user.email)


# ------------------------------------------------------------------
# /me routes
# ------------------------------------------------------------------

@router.get("/me")
def get_me(user_id: int = Depends(require_user), db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    return {"id": user.id, "email": user.email}


@router.get("/me/measurements")
def get_measurements(user_id: int = Depends(require_user), db: Session = Depends(get_db)):
    row = db.query(UserMeasurements).filter(UserMeasurements.user_id == user_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="No measurements saved yet.")
    return {"data": json.loads(row.data), "updated_at": row.updated_at}


@router.put("/me/measurements")
def save_measurements(
    payload: MeasurementsPayload,
    user_id: int = Depends(require_user),
    db: Session = Depends(get_db),
):
    row = db.query(UserMeasurements).filter(UserMeasurements.user_id == user_id).first()
    if row:
        row.data = json.dumps(payload.data)
    else:
        row = UserMeasurements(user_id=user_id, data=json.dumps(payload.data))
        db.add(row)
    db.commit()
    db.refresh(row)
    return {"data": json.loads(row.data), "updated_at": row.updated_at}
