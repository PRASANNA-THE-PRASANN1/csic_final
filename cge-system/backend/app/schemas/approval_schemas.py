"""
Pydantic schemas for Approval operations.
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


# --- Request Schemas ---

class ApprovalCreate(BaseModel):
    approver_id: str = Field(..., min_length=1, max_length=100)
    approver_name: str = Field(..., min_length=2, max_length=255)
    approver_role: str = Field(
        ..., pattern="^(branch_manager|credit_manager|ceo|board_member)$"
    )
    comments: Optional[str] = None
    ip_address: Optional[str] = None


# --- Response Schemas ---

class ApprovalResponse(BaseModel):
    id: int
    loan_id: str
    approver_id: str
    approver_name: str
    approver_role: str
    loan_hash: str
    approver_signature: str
    comments: Optional[str] = None
    approved_at: datetime
    ip_address: Optional[str] = None

    class Config:
        from_attributes = True
