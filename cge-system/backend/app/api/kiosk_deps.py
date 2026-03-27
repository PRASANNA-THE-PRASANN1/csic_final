"""
Kiosk session token authentication middleware.
Unlike JWT auth, kiosk endpoints use session tokens that are
validated against the kiosk_sessions table.
"""

from fastapi import Header, HTTPException
from typing import Optional
from sqlalchemy.orm import Session

from app.services.kiosk_session_service import KioskSessionService


def get_kiosk_session(loan_id: str, x_session_token: Optional[str] = Header(None)):
    """
    FastAPI dependency for kiosk endpoints. Validates session token from
    X-Session-Token header and returns a dict with loan_id and session info.
    """
    if not x_session_token:
        raise HTTPException(status_code=401, detail="Missing X-Session-Token header")

    from app.db.database import SessionLocal
    db = SessionLocal()
    try:
        service = KioskSessionService()
        session = service.validate_session_token(db, loan_id, x_session_token)
        service.update_activity(db, loan_id)
        return {
            "loan_id": loan_id,
            "session_id": session.session_id,
            "session_status": session.session_status,
        }
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))
    finally:
        db.close()
