"""
FarmerConsent SQLAlchemy model.
Stores the cryptographic proof of farmer agreement to exact loan terms.
Uses Bank KYC + OTP + local biometric for realistic identity verification.
"""

from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, Text, ForeignKey, JSON
from sqlalchemy.orm import relationship
from datetime import datetime, timezone

from app.db.database import Base


class FarmerConsent(Base):
    __tablename__ = "farmer_consents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    loan_id = Column(String(50), ForeignKey("loans.loan_id"), unique=True, nullable=False)
    loan_hash = Column(String(64), nullable=False)
    farmer_signature = Column(Text, nullable=False)  # base64-encoded Ed25519 signature
    consent_method = Column(String(50), default="bank_kyc_otp_local_biometric")
    otp_verified = Column(String(10), nullable=True)  # last 4 digits of OTP
    ip_address = Column(String(50), nullable=True)
    device_info = Column(JSON, nullable=True)
    consented_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    consent_token = Column(JSON, nullable=True)  # full consent token with all metadata

    # Bank KYC Verification
    bank_kyc_verified = Column(Boolean, default=False)  # verified against bank customer master
    otp_reference_id = Column(String(50), nullable=True)  # OTP reference for audit trail

    # Local Biometric Capture (NOT sent to UIDAI)
    fingerprint_hash = Column(String(64), nullable=True)  # SHA-256 of local biometric capture
    fingerprint_captured_at = Column(DateTime, nullable=True)

    # Live Photo Capture (Fraud Type 3 – Forgery Prevention)
    live_photo_hash = Column(String(64), nullable=True)  # SHA-256 of the captured photo
    gps_latitude = Column(Float, nullable=True)
    gps_longitude = Column(Float, nullable=True)
    consent_device_fingerprint = Column(Text, nullable=True)  # JSON device fingerprint

    # Relationships
    loan = relationship("Loan", back_populates="farmer_consent")

    def __repr__(self):
        return f"<FarmerConsent(loan_id={self.loan_id}, method={self.consent_method})>"
