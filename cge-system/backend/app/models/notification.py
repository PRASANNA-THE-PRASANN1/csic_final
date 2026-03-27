"""
Notification model Audit trail for all SMS notifications sent to farmers.

Every notification is recorded to:
1. Prove farmer was informed at each stage
2. Enable execution-time validation
3. Create non-repudiation evidence
"""

from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.database import Base


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    loan_id = Column(String(50), ForeignKey("loans.loan_id"), nullable=False, index=True)

    # Notification details
    notification_type = Column(
        String(50), nullable=False
    )  # loan_creation, consent_confirmation, disbursement
    recipient_mobile = Column(String(15), nullable=False)
    sms_content = Column(Text, nullable=False)

    # Delivery tracking
    sent_at = Column(DateTime(timezone=True), server_default=func.now())
    delivery_status = Column(
        String(20), default="sent"
    )  # sent, delivered, failed
    sms_gateway_response = Column(Text, nullable=True)  # JSON response

    # Relationship
    loan = relationship("Loan", backref="notifications")

    def __repr__(self):
        return (
            f"<Notification(loan_id={self.loan_id}, "
            f"type={self.notification_type}, "
            f"status={self.delivery_status})>"
        )
