"""
Loan SQLAlchemy model.
Stores farmer loan applications with cryptographic hash binding.
"""

from sqlalchemy import Column, String, Float, Integer, Boolean, DateTime, Text, JSON, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
import uuid


from app.db.database import Base


class Loan(Base):
    __tablename__ = "loans"

    id = Column(Integer, primary_key=True, autoincrement=True)
    loan_id = Column(String(50), unique=True, index=True, nullable=False)
    farmer_id = Column(String(100), index=True, nullable=True)
    farmer_name = Column(String(255), nullable=True)
    farmer_mobile = Column(String(15), nullable=True)
    amount = Column(Float, nullable=True)
    tenure_months = Column(Integer, nullable=True)
    interest_rate = Column(Float, nullable=True)
    purpose = Column(Text, nullable=True)

    # Farmer declaration linkage (Fraud Type 2)
    declaration_id = Column(String, ForeignKey("farmer_declarations.declaration_id"), nullable=True)
    farmer_declared_amount = Column(Float, nullable=True)
    amount_difference_reason = Column(String(500), nullable=True)
    amount_verified_by_senior = Column(String(100), nullable=True)

    loan_hash = Column(String(64), index=True, nullable=True)
    status = Column(
        String(50), default="kiosk_started"
    )  # kiosk_started, aadhaar_qr_scanned, aadhaar_verified, document_uploaded, ocr_confirmed,
    # kiosk_consented, kiosk_anchored, pending_clerk_review, pending_approvals,
    # manager_rejected, disbursement_rejected, cbs_validated, ready_for_execution, executed, anchored, rejected, kiosk_expired
    approval_tier = Column(String(20), nullable=True)  # tier_1, tier_2, tier_3, tier_4
    created_by = Column(String(100), nullable=True)  # clerk employee_id
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    metadata_json = Column(JSON, nullable=True)
    cbs_validated_at = Column(DateTime, nullable=True)  # CBS validation timestamp

    # Kiosk session fields
    kiosk_session_id = Column(String(64), nullable=True)
    aadhaar_verified_name = Column(String(255), nullable=True)
    document_hash = Column(String(64), nullable=True)
    kiosk_phase_anchor_hash = Column(String(64), nullable=True)
    kiosk_completed_at = Column(DateTime, nullable=True)
    assistance_session = Column(Boolean, default=False)

    # Clerk review fields
    clerk_reviewed_by = Column(String(100), nullable=True)
    clerk_accepted_at = Column(DateTime, nullable=True)
    clerk_rejected_at = Column(DateTime, nullable=True)
    clerk_review_opened_at = Column(DateTime, nullable=True)
    rejection_reason = Column(Text, nullable=True)
    rejection_category = Column(String(100), nullable=True)

    # Manager rejection fields
    manager_rejected_by = Column(String(100), nullable=True)
    manager_rejected_by_name = Column(String(255), nullable=True)
    manager_rejected_by_role = Column(String(100), nullable=True)
    manager_rejection_reason = Column(Text, nullable=True)
    manager_rejection_category = Column(String(100), nullable=True)
    manager_rejected_at = Column(DateTime, nullable=True)
    manager_rejection_signature = Column(Text, nullable=True)

    # Assisting employee fields (recorded at kiosk step 2)
    assisting_employee_name = Column(String(255), nullable=True)
    assisting_employee_id = Column(String(100), nullable=True)

    # IVR voice confirmation fields (60-second window consent)
    ivr_status = Column(String(30), nullable=True)  # pending / confirmed / rejected / failed / timed_out
    ivr_attempts = Column(Integer, default=0)
    ivr_confirmed_at = Column(DateTime, nullable=True)
    consent_final_method = Column(String(20), nullable=True)  # ivr / sms
    ivr_window_started_at = Column(DateTime, nullable=True)  # UTC start of 60s window
    consent_given_at = Column(DateTime, nullable=True)  # When farmer initiated consent

    # Relationships
    farmer_consent = relationship(
        "FarmerConsent", back_populates="loan", uselist=False, cascade="all, delete-orphan"
    )
    approvals = relationship("Approval", back_populates="loan", cascade="all, delete-orphan")
    blockchain_anchor = relationship(
        "BlockchainAnchor", back_populates="loan", uselist=False, cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<Loan(loan_id={self.loan_id}, farmer={self.farmer_name}, amount={self.amount}, status={self.status})>"
