"""
AadhaarService — simulates Aadhaar OTP authentication.
Production: calls UIDAI Authentication API under AUA licensing.
Demo: generates OTPs and logs them to terminal.
"""

import hashlib
import uuid
import random
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session

from app.models.consent_otp import ConsentOTPRecord
from app.models.kiosk_presence import KioskPresenceRecord
from app.models.kiosk_session import KioskSession
from app.models.loan import Loan


# Simulated eKYC name mapping for demo
AADHAAR_NAME_MAP = {
    "4521": "Ramesh Sharma",
    "7832": "Sita Devi",
    "3156": "Gopal Yadav",
    "6294": "Lakshmi Bai",
    "8471": "Mohan Patel",
    "1923": "Kamla Devi",
    "5047": "Raju Singh",
    "2385": "Sunita Kumari",
    "9160": "Harish Verma",
    "7534": "Meena Sharma",
    "4289": "Bhola Nath",
    "6107": "Durga Devi",
    "8653": "Pratap Singh",
    "3948": "Anita Bai",
    "7216": "Dinesh Kumar",
    "5839": "Pushpa Devi",
    "1472": "Kishan Lal",
    "9384": "Savitri Devi",
    "2761": "Vijay Sharma",
    "6095": "Radha Bai",
}


class AadhaarService:
    """Simulates Aadhaar OTP authentication for kiosk identity verification."""

    def initiate_auth(self, db: Session, aadhaar_last_four: str, mobile_last_four: str, loan_id: str):
        """Initiate Aadhaar OTP authentication."""
        # Validate inputs
        if not aadhaar_last_four or len(aadhaar_last_four) != 4 or not aadhaar_last_four.isdigit():
            raise ValueError("Aadhaar last four must be exactly 4 digits")
        if not mobile_last_four or len(mobile_last_four) != 4 or not mobile_last_four.isdigit():
            raise ValueError("Mobile last four must be exactly 4 digits")

        # Generate 6-digit OTP
        otp = f"{random.randint(100000, 999999)}"
        otp_hash = hashlib.sha256(otp.encode()).hexdigest()
        otp_reference_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        # Store OTP record
        otp_record = ConsentOTPRecord(
            loan_id=loan_id,
            otp_type="aadhaar_auth",
            otp_hash=otp_hash,
            otp_reference_id=otp_reference_id,
            mobile_last_four=mobile_last_four,
            issued_at=now,
            expires_at=now + timedelta(minutes=10),
        )
        db.add(otp_record)

        # Store Aadhaar info in presence record
        presence = db.query(KioskPresenceRecord).filter(
            KioskPresenceRecord.loan_id == loan_id
        ).first()
        if presence:
            presence.aadhaar_last_four = aadhaar_last_four
            presence.aadhaar_hash = hashlib.sha256(
                f"XXXX-XXXX-{aadhaar_last_four}".encode()
            ).hexdigest()
        else:
            presence = KioskPresenceRecord(
                loan_id=loan_id,
                aadhaar_last_four=aadhaar_last_four,
                aadhaar_hash=hashlib.sha256(
                    f"XXXX-XXXX-{aadhaar_last_four}".encode()
                ).hexdigest(),
            )
            db.add(presence)

        db.commit()

        # Log OTP to terminal (simulated SMS)
        # SECURITY NOTE: In production deployment, the OTP would be delivered exclusively
        # via SMS to the farmer's Aadhaar-registered mobile number through UIDAI's official
        # authentication API. The on-screen display is a demo accommodation for environments
        # without live UIDAI API access.
        print(f"AADHAAR OTP for loan {loan_id}: {otp}")

        return {
            "otp_reference_id": otp_reference_id,
            "mobile_last_four": mobile_last_four,
            "otp_display": otp,
            "message": "OTP generated successfully",
        }

    def verify_auth(self, db: Session, otp_reference_id: str, submitted_otp: str, loan_id: str):
        """Verify the submitted OTP against the stored hash."""
        otp_record = db.query(ConsentOTPRecord).filter(
            ConsentOTPRecord.otp_reference_id == otp_reference_id,
            ConsentOTPRecord.otp_type == "aadhaar_auth",
            ConsentOTPRecord.loan_id == loan_id,
        ).first()

        if not otp_record:
            raise ValueError("OTP record not found")

        if otp_record.used:
            raise ValueError("OTP has already been used")

        if datetime.now(timezone.utc).replace(tzinfo=None) > otp_record.expires_at:
            raise ValueError("OTP has expired")

        if otp_record.attempt_count >= 3:
            raise ValueError("Too many attempts. Please request a new OTP.")

        otp_record.attempt_count += 1
        submitted_hash = hashlib.sha256(submitted_otp.encode()).hexdigest()

        if submitted_hash != otp_record.otp_hash:
            db.commit()
            raise ValueError(f"Invalid OTP. Attempt {otp_record.attempt_count} of 3.")

        # OTP verified
        now = datetime.now(timezone.utc)
        otp_record.used = True
        otp_record.verified_at = now

        # Update presence record
        presence = db.query(KioskPresenceRecord).filter(
            KioskPresenceRecord.loan_id == loan_id
        ).first()
        if presence:
            presence.aadhaar_otp_verified = True
            presence.aadhaar_verified_at = now
            # Simulate eKYC name return
            farmer_name = self.get_ekyc_name(presence.aadhaar_last_four)
            presence.aadhaar_verified_name = farmer_name
        else:
            farmer_name = "Unknown Farmer"

        # Update loan record
        loan = db.query(Loan).filter(Loan.loan_id == loan_id).first()
        if loan:
            loan.aadhaar_verified_name = farmer_name
            loan.status = "aadhaar_verified"

        # Update kiosk session
        session = db.query(KioskSession).filter(KioskSession.loan_id == loan_id).first()
        if session:
            session.session_status = "aadhaar_verified"

        db.commit()

        return {
            "verified": True,
            "farmer_name": farmer_name,
            "session_status": "aadhaar_verified",
        }

    def get_ekyc_name(self, aadhaar_last_four: str) -> str:
        """Return simulated name based on Aadhaar last four digits.
        Production: calls UIDAI eKYC API for actual demographic data."""
        return AADHAAR_NAME_MAP.get(aadhaar_last_four, f"Farmer-{aadhaar_last_four}")
