"""
BlockchainAnchor SQLAlchemy model.
Links a fully-approved loan to its immutable blockchain proof.
"""

from sqlalchemy import Column, String, Integer, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime, timezone

from app.db.database import Base


class BlockchainAnchor(Base):
    __tablename__ = "blockchain_anchors"

    id = Column(Integer, primary_key=True, autoincrement=True)
    loan_id = Column(String(50), ForeignKey("loans.loan_id"), unique=True, nullable=False)
    consent_hash = Column(String(64), nullable=False)  # SHA-256 of final consent token
    block_number = Column(Integer, index=True, nullable=False)
    transaction_hash = Column(String(128), nullable=False)
    anchored_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    blockchain_response = Column(Text, nullable=True)  # full response JSON for debugging

    # Relationships
    loan = relationship("Loan", back_populates="blockchain_anchor")

    def __repr__(self):
        return f"<BlockchainAnchor(loan_id={self.loan_id}, block={self.block_number})>"
