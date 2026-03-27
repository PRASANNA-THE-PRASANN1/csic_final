"""
Pydantic schemas for disbursement consent (Fraud Type 1 – Benami Prevention).
"""

from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field


class DisbursementConsentCreate(BaseModel):
    """Request body for creating a disbursement consent."""
    account_number: str = Field(..., min_length=8, max_length=18, pattern=r"^\d{8,18}$")
    ifsc_code: str = Field(..., min_length=11, max_length=11,  pattern=r"^[A-Za-z]{4}0[A-Za-z0-9]{6}$")
    account_holder_name: str = Field(..., min_length=2, max_length=255)


class DisbursementConsentResponse(BaseModel):
    """Response for disbursement consent."""
    id: int
    loan_id: str
    account_number: str
    account_holder_name: str
    ifsc_code: str
    penny_drop_verified: bool
    penny_drop_name_matched: bool
    bank_name: Optional[str] = None
    disbursement_hash: str
    consented_at: Optional[datetime] = None

    class Config:
        from_attributes = True
