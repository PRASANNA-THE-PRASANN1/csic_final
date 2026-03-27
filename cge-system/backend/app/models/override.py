"""
OverrideRequest model — CEO + Auditor dual-signature override governance.
Records override requests with cryptographic co-signatures.
No UPDATE or DELETE operations are ever issued by the application.
"""

from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.database import Base


class OverrideRequest(Base):
    __tablename__ = "override_requests"

    id = Column(Integer, primary_key=True, autoincrement=True)
    loan_id = Column(String(50), ForeignKey("loans.loan_id"), nullable=False, index=True)
    requested_by = Column(String(100), nullable=False)  # CEO user_id
    co_signed_by = Column(String(100), nullable=True)   # Auditor user_id, null until co-signed
    ceo_signature = Column(Text, nullable=False)         # Ed25519 signature of loan_hash
    auditor_signature = Column(Text, nullable=True)      # Ed25519 signature of loan_hash
    reason_text = Column(Text, nullable=False)
    status = Column(String(30), default="pending_cosign")  # pending_cosign, approved, rejected
    anchor_block_id = Column(Integer, ForeignKey("blockchain_anchors.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    loan = relationship("Loan", backref="override_requests")

    def __repr__(self):
        return f"<OverrideRequest(loan_id={self.loan_id}, status={self.status})>"
