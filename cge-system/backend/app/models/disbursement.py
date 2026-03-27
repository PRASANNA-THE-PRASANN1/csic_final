"""
DisbursementConsent model – records farmer's bank account for disbursement
with penny-drop verification to prevent benami (proxy) fraud.
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, Boolean, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.database import Base


class DisbursementConsent(Base):
    __tablename__ = "disbursement_consents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    loan_id = Column(String, ForeignKey("loans.loan_id"), nullable=False, unique=True)

    # Farmer's bank account details
    account_number = Column(String(20), nullable=False)
    account_holder_name = Column(String(255), nullable=False)
    ifsc_code = Column(String(11), nullable=False)

    # Penny-drop verification results
    penny_drop_verified = Column(Boolean, default=False)
    penny_drop_name_matched = Column(Boolean, default=False)
    penny_drop_response = Column(Text, nullable=True)  # JSON response from penny-drop API

    # Cryptographic proof
    disbursement_hash = Column(String(64), nullable=False)
    farmer_disbursement_signature = Column(Text, nullable=True)

    # Metadata
    ip_address = Column(String(45), nullable=True)
    device_info = Column(Text, nullable=True)
    consented_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationship
    loan = relationship("Loan", backref="disbursement_consent")
