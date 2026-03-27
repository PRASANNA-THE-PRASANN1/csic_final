"""
KioskSession model — tracks the farmer's entire kiosk session lifecycle.
Sessions are short-lived (30 min max) and use session tokens instead of JWT.
Every session has a mandatory assisting employee assigned at start.
"""

from sqlalchemy import Column, Integer, String, DateTime, Text
from sqlalchemy.sql import func
from datetime import datetime, timezone

from app.db.database import Base


class KioskSession(Base):
    __tablename__ = "kiosk_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(64), unique=True, index=True, nullable=False)
    loan_id = Column(String(50), unique=True, index=True, nullable=False)
    session_token = Column(String(128), nullable=False)
    session_token_expires_at = Column(DateTime, nullable=False)
    session_status = Column(String(30), default="started")
    # started → aadhaar_qr_scanned → face_matched → aadhaar_verified → document_uploaded → ocr_confirmed,
    # consented → completed | expired
    session_started_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    session_completed_at = Column(DateTime, nullable=True)
    last_activity_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    ip_address = Column(String(50), nullable=True)
    kiosk_device_fingerprint = Column(Text, nullable=True)
    # Mandatory assisting employee — assigned at session start
    assisting_employee_name = Column(String(255), nullable=True)
    assisting_employee_id = Column(String(100), nullable=True)

    def __repr__(self):
        return f"<KioskSession(session_id={self.session_id}, loan_id={self.loan_id}, status={self.session_status})>"
