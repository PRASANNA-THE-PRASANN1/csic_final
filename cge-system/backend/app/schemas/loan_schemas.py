"""
Pydantic schemas for Loan operations.
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Any
from datetime import datetime


# --- Request Schemas ---

class LoanCreate(BaseModel):
    farmer_id: str = Field(..., min_length=1, max_length=100)
    farmer_name: str = Field(..., min_length=2, max_length=255)
    farmer_mobile: str = Field(..., min_length=10, max_length=15)
    amount: float = Field(..., gt=0)
    tenure_months: int = Field(..., gt=0)
    interest_rate: float = Field(..., gt=0)
    purpose: str = Field(..., min_length=5)
    created_by: Optional[str] = None
    # Fraud Prevention: Declaration linkage
    declaration_id: Optional[str] = None
    amount_difference_reason: Optional[str] = None


# --- Response Schemas ---

class LoanResponse(BaseModel):
    id: int
    loan_id: str
    farmer_id: Optional[str] = None
    farmer_name: Optional[str] = None
    farmer_mobile: Optional[str] = None
    amount: Optional[float] = None
    tenure_months: Optional[int] = None
    interest_rate: Optional[float] = None
    purpose: Optional[str] = None
    loan_hash: Optional[str] = None
    status: str
    approval_tier: Optional[str] = None
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    # Fraud Prevention fields
    declaration_id: Optional[str] = None
    farmer_declared_amount: Optional[float] = None
    amount_difference_reason: Optional[str] = None
    metadata_json: Optional[Any] = None
    cbs_validated_at: Optional[datetime] = None
    # Kiosk fields
    kiosk_session_id: Optional[str] = None
    aadhaar_verified_name: Optional[str] = None
    document_hash: Optional[str] = None
    kiosk_phase_anchor_hash: Optional[str] = None
    kiosk_completed_at: Optional[datetime] = None
    assistance_session: Optional[bool] = None
    # Manager rejection fields
    manager_rejected_by: Optional[str] = None
    manager_rejected_by_name: Optional[str] = None
    manager_rejected_by_role: Optional[str] = None
    manager_rejection_reason: Optional[str] = None
    manager_rejection_category: Optional[str] = None
    manager_rejected_at: Optional[datetime] = None
    manager_rejection_signature: Optional[str] = None

    class Config:
        from_attributes = True


class LoanListResponse(BaseModel):
    loans: List[LoanResponse]
    total: int

