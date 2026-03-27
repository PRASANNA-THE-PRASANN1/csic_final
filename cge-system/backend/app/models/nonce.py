"""
UsedNonce model — tracks consumed nonces for replay attack prevention.
Each consent submission includes a unique nonce that can only be used once.
"""

from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func

from app.db.database import Base


class UsedNonce(Base):
    __tablename__ = "used_nonces"

    id = Column(Integer, primary_key=True, autoincrement=True)
    nonce = Column(String(64), unique=True, index=True, nullable=False)
    loan_id = Column(String(50), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<UsedNonce(nonce={self.nonce[:8]}..., loan_id={self.loan_id})>"
