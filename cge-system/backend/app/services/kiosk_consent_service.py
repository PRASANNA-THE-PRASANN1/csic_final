"""
KioskConsentService — handles the final farmer consent event.
The second OTP constitutes consent (not authentication).
"""

import hashlib
import uuid
import json
import random
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session

from app.models.consent_otp import ConsentOTPRecord
from app.models.kiosk_session import KioskSession
from app.models.kiosk_presence import KioskPresenceRecord
from app.models.loan_document import LoanDocument
from app.models.loan import Loan
from app.models.consent import FarmerConsent
from app.models.nonce import UsedNonce


class KioskConsentService:
    """Handles the kiosk consent OTP flow and builds the consent evidence package."""

    def initiate_consent_otp(self, db: Session, loan_id: str):
        """Generate and store a consent OTP."""
        otp = f"{random.randint(100000, 999999)}"
        otp_hash = hashlib.sha256(otp.encode()).hexdigest()
        otp_reference_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        otp_record = ConsentOTPRecord(
            loan_id=loan_id,
            otp_type="loan_consent",
            otp_hash=otp_hash,
            otp_reference_id=otp_reference_id,
            issued_at=now,
            expires_at=now + timedelta(minutes=10),
        )
        db.add(otp_record)
        db.commit()

        print(f"CONSENT OTP for loan {loan_id}: {otp}")

        return {"otp_reference_id": otp_reference_id}

    def verify_consent(self, db: Session, loan_id: str, otp_reference_id: str, submitted_otp: str, nonce: str):
        """Verify consent OTP with replay protection."""
        # Nonce replay protection
        existing_nonce = db.query(UsedNonce).filter(UsedNonce.nonce == nonce).first()
        if existing_nonce:
            raise ValueError("This consent request has already been processed (replay detected)")
        db.add(UsedNonce(nonce=nonce, loan_id=loan_id))
        db.flush()

        # Find OTP record
        otp_record = db.query(ConsentOTPRecord).filter(
            ConsentOTPRecord.otp_reference_id == otp_reference_id,
            ConsentOTPRecord.otp_type == "loan_consent",
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

        # OTP verified — record consent
        now = datetime.now(timezone.utc)
        otp_record.used = True
        otp_record.verified_at = now

        # Update session and loan
        session = db.query(KioskSession).filter(KioskSession.loan_id == loan_id).first()
        if session:
            session.session_status = "consented"

        loan = db.query(Loan).filter(Loan.loan_id == loan_id).first()
        if loan:
            loan.status = "kiosk_consented"

        # Create FarmerConsent record
        consent_token = self.build_consent_token(db, loan_id)
        farmer_consent = FarmerConsent(
            loan_id=loan_id,
            loan_hash=loan.loan_hash if loan else "",
            farmer_signature=f"kiosk_consent_{loan_id}_{now.isoformat()}",
            consent_method="kiosk_aadhaar_otp",
            otp_verified=submitted_otp[-4:],
            ip_address=session.ip_address if session else "127.0.0.1",
            consented_at=now,
            bank_kyc_verified=True,
            consent_token=consent_token,
        )

        # Check if consent already exists (shouldn't, but safe guard)
        existing_consent = db.query(FarmerConsent).filter(FarmerConsent.loan_id == loan_id).first()
        if not existing_consent:
            db.add(farmer_consent)

        db.commit()

        consent_hash = hashlib.sha256(
            json.dumps(consent_token, sort_keys=True, separators=(",", ":"), default=str).encode()
        ).hexdigest()

        return {
            "consented": True,
            "consent_token_hash": consent_hash,
            "session_status": "consented",
        }

    def build_consent_token(self, db: Session, loan_id: str) -> dict:
        """Build complete consent evidence package."""
        session = db.query(KioskSession).filter(KioskSession.loan_id == loan_id).first()
        loan = db.query(Loan).filter(Loan.loan_id == loan_id).first()
        presence = db.query(KioskPresenceRecord).filter(KioskPresenceRecord.loan_id == loan_id).first()
        loan_doc = db.query(LoanDocument).filter(LoanDocument.loan_id == loan_id).first()

        return {
            "session_id": session.session_id if session else None,
            "loan_id": loan_id,
            "aadhaar_hash": presence.aadhaar_hash if presence else None,
            "aadhaar_verified_name": presence.aadhaar_verified_name if presence else None,
            "aadhaar_last_four": presence.aadhaar_last_four if presence else None,
            "document_hash": loan_doc.document_hash if loan_doc else None,
            "signature_region_hash": loan_doc.signature_region_hash if loan_doc else None,
            "farmer_confirmed_amount": loan_doc.farmer_confirmed_amount if loan_doc else None,
            "farmer_confirmed_purpose": loan_doc.farmer_confirmed_purpose if loan_doc else None,
            "photo_hash": presence.photo_hash if presence else None,
            "gps_latitude": presence.gps_latitude if presence else None,
            "gps_longitude": presence.gps_longitude if presence else None,
            "device_fingerprint_hash": presence.device_fingerprint_hash if presence else None,
            "aadhaar_otp_verified_at": presence.aadhaar_verified_at.isoformat() if presence and presence.aadhaar_verified_at else None,
            "consent_otp_verified_at": datetime.now(timezone.utc).isoformat(),
            "kiosk_device_fingerprint": session.kiosk_device_fingerprint if session else None,
            "terms_accepted_at": presence.terms_accepted_at.isoformat() if presence and presence.terms_accepted_at else None,
            "assisting_employee_name": presence.assisting_employee_name if presence else None,
            "assisting_employee_id": presence.assisting_employee_id if presence else None,
        }
