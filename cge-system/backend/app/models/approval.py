"""
Approval SQLAlchemy model.
Stores each manager's cryptographic approval signature bound to the loan hash.
"""

from sqlalchemy import Column, String, Integer, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime, timezone

from app.db.database import Base


class Approval(Base):
    __tablename__ = "approvals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    loan_id = Column(String(50), ForeignKey("loans.loan_id"), index=True, nullable=False)
    approver_id = Column(String(100), nullable=False)  # e.g. EMP001
    approver_name = Column(String(255), nullable=False)
    approver_role = Column(
        String(50), nullable=False
    )  # branch_manager, credit_manager, ceo, board_member
    loan_hash = Column(String(64), nullable=False)  # must match loan.loan_hash
    approver_signature = Column(Text, nullable=False)  # base64-encoded Ed25519 signature
    comments = Column(Text, nullable=True)
    approved_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    ip_address = Column(String(50), nullable=True)

    # Relationships
    loan = relationship("Loan", back_populates="approvals")

    def __repr__(self):
        return f"<Approval(loan_id={self.loan_id}, role={self.approver_role}, approver={self.approver_name})>"
