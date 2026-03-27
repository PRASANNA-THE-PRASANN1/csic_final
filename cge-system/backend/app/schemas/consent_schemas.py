"""
Pydantic schemas for Farmer Consent operations.
Updated for Bank KYC + OTP + local biometric flow.
"""

from pydantic import BaseModel, Field
from typing import Optional, Any
from datetime import datetime


# --- Request Schemas ---

class FarmerConsentCreate(BaseModel):
    otp: str = Field(..., min_length=4, max_length=10)
    nonce: str = Field(..., min_length=1, description="Unique UUID for replay protection")
    device_info: Optional[dict] = None
    ip_address: Optional[str] = None
    # Bank KYC verification
    bank_kyc_verified: Optional[bool] = False
    otp_reference_id: Optional[str] = None
    # Local biometric capture (NOT sent to UIDAI)
    fingerprint_hash: Optional[str] = None  # SHA-256 hash of locally captured fingerprint
    # Fraud Type 3: Live photo capture
    live_photo_base64: Optional[str] = None  # base64-encoded photo
    gps_latitude: Optional[float] = None
    gps_longitude: Optional[float] = None
    device_fingerprint: Optional[str] = None  # JSON string


# --- Response Schemas ---

class FarmerConsentResponse(BaseModel):
    id: int
    loan_id: str
    loan_hash: str
    farmer_signature: str
    consent_method: str
    otp_verified: Optional[str] = None
    ip_address: Optional[str] = None
    consented_at: datetime
    consent_token: Optional[Any] = None
    # Bank KYC fields
    bank_kyc_verified: Optional[bool] = None
    otp_reference_id: Optional[str] = None
    fingerprint_hash: Optional[str] = None
    fingerprint_captured_at: Optional[datetime] = None
    # Fraud Type 3: Forgery prevention
    live_photo_hash: Optional[str] = None
    gps_latitude: Optional[float] = None
    gps_longitude: Optional[float] = None

    class Config:
        from_attributes = True
