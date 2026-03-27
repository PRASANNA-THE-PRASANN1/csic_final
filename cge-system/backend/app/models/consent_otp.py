"""
ConsentOTPRecord model — tracks OTP issuance and verification for both
Aadhaar authentication and loan consent events. Never stores raw OTP values.
"""

from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from datetime import datetime, timezone

from app.db.database import Base


class ConsentOTPRecord(Base):
    __tablename__ = "consent_otp_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    loan_id = Column(String(50), ForeignKey("loans.loan_id"), nullable=False, index=True)
    otp_type = Column(String(20), nullable=False)  # 'aadhaar_auth' or 'loan_consent'
    otp_hash = Column(String(64), nullable=False)  # SHA-256 of OTP value
    otp_reference_id = Column(String(64), nullable=False, unique=True)
    mobile_last_four = Column(String(4), nullable=True)
    issued_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    expires_at = Column(DateTime, nullable=False)  # 10 minutes from issued
    verified_at = Column(DateTime, nullable=True)
    used = Column(Boolean, default=False)
    attempt_count = Column(Integer, default=0)

    def __repr__(self):
        return f"<ConsentOTPRecord(loan_id={self.loan_id}, type={self.otp_type}, used={self.used})>"
