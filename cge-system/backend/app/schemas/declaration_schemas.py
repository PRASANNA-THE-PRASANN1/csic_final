"""
Pydantic schemas for farmer self-declaration (Fraud Type 2 Amount Inflation Prevention).
"""

from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field


class FarmerDeclarationCreate(BaseModel):
    """Request body for farmer self-declaration of loan requirements."""
    farmer_id: str = Field(..., min_length=1, max_length=100)
    farmer_name: str = Field(..., min_length=2, max_length=255)
    farmer_mobile: str = Field(..., pattern=r"^\d{10}$")
    declared_amount: float = Field(..., gt=0, le=10_000_000)
    purpose: str = Field(..., min_length=3, max_length=500)
    otp: str = Field(..., min_length=6, max_length=6)


class FarmerDeclarationResponse(BaseModel):
    """Response for farmer declaration."""
    declaration_id: str
    farmer_id: str
    farmer_name: str
    farmer_mobile: str
    declared_amount: float
    purpose: str
    declaration_hash: str
    otp_verified: bool
    status: str
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True
