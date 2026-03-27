"""
FastAPI dependency injection.
Provides service instances and JWT authentication to route handlers.
"""

import os
from fastapi import Depends, HTTPException, Header
from typing import Optional
from jose import jwt, JWTError
from dotenv import load_dotenv

from app.services.crypto_service import CryptoService
from app.services.policy_engine import PolicyEngine
from app.services.consent_engine import ConsentEngine
from app.services.blockchain_service import BlockchainService
from app.services.penny_drop_service import PennyDropService
from app.services.sms_service import SMSService
from app.services.identity_service import IdentityService
from app.services.notification_service import NotificationService
from app.services.kiosk_session_service import KioskSessionService
from app.services.aadhaar_service import AadhaarService
from app.services.document_service import DocumentService
from app.services.kiosk_consent_service import KioskConsentService
from app.services.kiosk_anchor_service import KioskAnchorService
from app.services.ivr_service import IVRService

load_dotenv()
SECRET_KEY = os.getenv("JWT_SECRET_KEY", os.getenv("SECRET_KEY", "fallback-secret"))
ALGORITHM = "HS256"


# ── JWT Authentication Dependency ──

async def get_current_user(authorization: Optional[str] = Header(None)) -> dict:
    """
    Extract and verify JWT Bearer token from Authorization header.
    Returns user dict with user_id, role, name.
    Raises HTTP 401 on invalid/expired/missing token.
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    parts = authorization.split(" ")
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Invalid Authorization header format")

    token = parts[1]
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        role = payload.get("role")
        name = payload.get("name")
        if not user_id or not role:
            raise HTTPException(status_code=401, detail="Invalid token payload")
        return {"user_id": user_id, "role": role, "name": name}
    except JWTError:
        raise HTTPException(status_code=401, detail="Token is invalid or expired")


def require_roles(*allowed_roles):
    """
    Returns a dependency that checks current_user.role against allowed_roles.
    Raises HTTP 403 if role doesn't match.
    """
    async def _check(current_user: dict = Depends(get_current_user)):
        if current_user["role"] not in allowed_roles:
            raise HTTPException(
                status_code=403,
                detail=f"Access denied. Required roles: {', '.join(allowed_roles)}"
            )
        return current_user
    return _check


# ── Service Dependencies ──

def get_crypto_service() -> CryptoService:
    return CryptoService()


def get_policy_engine() -> PolicyEngine:
    return PolicyEngine()


def get_consent_engine() -> ConsentEngine:
    return ConsentEngine()


def get_blockchain_service() -> BlockchainService:
    return BlockchainService()


def get_penny_drop_service() -> PennyDropService:
    return PennyDropService()


def get_sms_service() -> SMSService:
    return SMSService()


def get_identity_service() -> IdentityService:
    return IdentityService()


def get_notification_service() -> NotificationService:
    return NotificationService()


def get_kiosk_session_service() -> KioskSessionService:
    return KioskSessionService()


def get_aadhaar_service() -> AadhaarService:
    return AadhaarService()


def get_document_service() -> DocumentService:
    return DocumentService()


def get_kiosk_consent_service() -> KioskConsentService:
    return KioskConsentService()


def get_kiosk_anchor_service() -> KioskAnchorService:
    return KioskAnchorService()


def get_ivr_service() -> IVRService:
    return IVRService()

