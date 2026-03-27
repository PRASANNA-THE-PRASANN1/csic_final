"""
FarmerDeclaration model – records farmer's self-declared loan requirement
BEFORE the clerk enters any details, preventing amount inflation fraud.
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, Text, Boolean, DateTime
from sqlalchemy.sql import func

from app.db.database import Base


class FarmerDeclaration(Base):
    __tablename__ = "farmer_declarations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    declaration_id = Column(String, unique=True, nullable=False, index=True)

    # Farmer details
    farmer_id = Column(String, nullable=False, index=True)
    farmer_name = Column(String(255), nullable=False)
    farmer_mobile = Column(String(15), nullable=False)

    # Self-declared loan details
    declared_amount = Column(Float, nullable=False)
    purpose = Column(String(500), nullable=False)

    # Cryptographic proof
    declaration_hash = Column(String(64), nullable=False)
    declaration_signature = Column(Text, nullable=True)  # Ed25519 signature

    # Verification
    otp_verified = Column(Boolean, default=False)

    # Status
    status = Column(String(30), default="active")  # active, linked, expired

    created_at = Column(DateTime(timezone=True), server_default=func.now())
