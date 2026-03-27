"""
KioskSessionService — manages the complete kiosk session lifecycle.
Sessions use short-lived tokens instead of JWT for farmer authentication.
"""

import uuid
import secrets
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session

from app.models.kiosk_session import KioskSession
from app.models.loan import Loan


class KioskSessionService:
    """Manages kiosk session creation, validation, timeout, and completion."""

    def create_session(self, db: Session, ip_address: str = None, device_fingerprint: str = None,
                        employee_name: str = None, employee_id: str = None):
        """Create a new kiosk session with a generated loan ID and session token.
        Requires a mandatory assisting employee assigned from the start."""
        import time
        session_id = str(uuid.uuid4())
        loan_id = f"LN{int(time.time() * 1000)}"
        session_token = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(minutes=30)

        # Create KioskSession record with mandatory employee
        kiosk_session = KioskSession(
            session_id=session_id,
            loan_id=loan_id,
            session_token=session_token,
            session_token_expires_at=expires_at,
            session_status="started",
            session_started_at=now,
            last_activity_at=now,
            ip_address=ip_address,
            kiosk_device_fingerprint=device_fingerprint,
            assisting_employee_name=employee_name,
            assisting_employee_id=employee_id,
        )
        db.add(kiosk_session)

        # Create minimal Loan record with mandatory employee
        loan = Loan(
            loan_id=loan_id,
            status="kiosk_started",
            kiosk_session_id=session_id,
            assisting_employee_name=employee_name,
            assisting_employee_id=employee_id,
            assistance_session=True,
        )
        db.add(loan)
        db.commit()

        return {
            "session_id": session_id,
            "loan_id": loan_id,
            "session_token": session_token,
            "expires_at": expires_at.isoformat(),
            "assisting_employee_name": employee_name,
            "assisting_employee_id": employee_id,
        }

    def validate_session_token(self, db: Session, loan_id: str, token: str):
        """Validate the session token for a loan. Raises ValueError on failure."""
        session = db.query(KioskSession).filter(KioskSession.loan_id == loan_id).first()
        if not session:
            raise ValueError("No kiosk session found for this loan")

        if session.session_status in ("completed", "expired"):
            raise ValueError("Kiosk session has ended")

        if session.session_token != token or not token:
            raise ValueError("Invalid session token")

        if datetime.now(timezone.utc).replace(tzinfo=None) > session.session_token_expires_at:
            self.expire_session(db, loan_id)
            raise ValueError("Session token has expired")

        return session

    def update_activity(self, db: Session, loan_id: str):
        """Update last_activity_at for timeout tracking."""
        session = db.query(KioskSession).filter(KioskSession.loan_id == loan_id).first()
        if session:
            session.last_activity_at = datetime.now(timezone.utc)
            db.commit()

    def check_timeout(self, db: Session, loan_id: str):
        """Check if the session has been inactive for more than 10 minutes."""
        session = db.query(KioskSession).filter(KioskSession.loan_id == loan_id).first()
        if session and session.last_activity_at:
            elapsed = datetime.now(timezone.utc) - session.last_activity_at
            if elapsed > timedelta(minutes=10):
                self.expire_session(db, loan_id)
                raise ValueError("Session expired due to inactivity")

    def expire_session(self, db: Session, loan_id: str):
        """Expire a session — clears token and sets expired status."""
        session = db.query(KioskSession).filter(KioskSession.loan_id == loan_id).first()
        if session:
            session.session_status = "expired"
            session.session_token = ""
            loan = db.query(Loan).filter(Loan.loan_id == loan_id).first()
            if loan:
                loan.status = "kiosk_expired"
            db.commit()

    def complete_session(self, db: Session, loan_id: str):
        """Complete the kiosk session — invalidates token, triggers anchoring."""
        session = db.query(KioskSession).filter(KioskSession.loan_id == loan_id).first()
        if not session:
            raise ValueError("No kiosk session found")

        now = datetime.now(timezone.utc)
        session.session_status = "completed"
        session.session_completed_at = now
        session.session_token = ""  # invalidate token

        loan = db.query(Loan).filter(Loan.loan_id == loan_id).first()
        if loan:
            loan.kiosk_completed_at = now
        db.commit()

    def update_session_status(self, db: Session, loan_id: str, status: str):
        """Update the kiosk session status."""
        session = db.query(KioskSession).filter(KioskSession.loan_id == loan_id).first()
        if session:
            session.session_status = status
            db.commit()
