from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint

from database import Base


class User(Base):
    __tablename__ = "users"

    id              = Column(Integer, primary_key=True)
    email           = Column(String, unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=False)
    created_at      = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class UserMeasurements(Base):
    __tablename__ = "user_measurements"

    id         = Column(Integer, primary_key=True)
    user_id    = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True)
    data       = Column(Text, nullable=False)   # JSON blob: {"bust": 92, "waist": 74, ...}
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
