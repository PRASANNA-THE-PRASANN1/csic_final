"""
API routes for the CGE System.
Endpoints for loans, farmer consent, manager approval, execution, audit,
identity verification, notifications, CBS validation, dashboard, override governance,
consent certificate, and blockchain verification.

Security features:
- JWT HS256 authentication with role-based access control (§2.2)
- bcrypt password verification (§2.1)
- Idempotency checks on mutating endpoints (§2.6)
- OTP rate limiting (§2.7)
- Nonce-based replay protection (§2.8)
"""

import os
import io
import time
import json
import asyncio
import hashlib
from collections import defaultdict
import json
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Body, Header, Request, Form
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func as sql_func
from datetime import datetime, timezone, timedelta
from typing import Optional
from jose import jwt, JWTError
from passlib.hash import bcrypt as bcrypt_hash
from dotenv import load_dotenv

from app.db.database import get_db
from app.models.loan import Loan
from app.models.consent import FarmerConsent
from app.models.approval import Approval
from app.models.blockchain import BlockchainAnchor
from app.models.disbursement import DisbursementConsent
from app.models.declaration import FarmerDeclaration
from app.models.notification import Notification
from app.models.user import User
from app.models.nonce import UsedNonce
from app.models.override import OverrideRequest
from app.models.kiosk_session import KioskSession
from app.models.kiosk_presence import KioskPresenceRecord
from app.models.loan_document import LoanDocument
from app.models.consent_otp import ConsentOTPRecord
from app.schemas.loan_schemas import LoanCreate, LoanResponse, LoanListResponse
from app.schemas.consent_schemas import FarmerConsentCreate, FarmerConsentResponse
from app.schemas.approval_schemas import ApprovalCreate, ApprovalResponse
from app.schemas.disbursement_schemas import DisbursementConsentCreate, DisbursementConsentResponse
from app.schemas.declaration_schemas import FarmerDeclarationCreate, FarmerDeclarationResponse
from app.api.deps import (
    get_crypto_service,
    get_policy_engine,
    get_consent_engine,
    get_blockchain_service,
    get_penny_drop_service,
    get_sms_service,
    get_identity_service,
    get_notification_service,
    get_current_user,
    require_roles,
    get_kiosk_session_service,
    get_aadhaar_service,
    get_document_service,
    get_kiosk_consent_service,
    get_kiosk_anchor_service,
    get_ivr_service,
)
from app.services.crypto_service import CryptoService
from app.services.policy_engine import PolicyEngine
from app.services.consent_engine import ConsentEngine
from app.services.blockchain_service import BlockchainService
from app.services.penny_drop_service import PennyDropService
from app.services.sms_service import SMSService
from app.services.identity_service import IdentityService
from app.services.notification_service import NotificationService
from app.services.cbs_service import CBSService
from app.services.override_service import OverrideService
from app.services.kiosk_session_service import KioskSessionService
from app.services.aadhaar_service import AadhaarService
from app.services.document_service import DocumentService
from app.services.kiosk_consent_service import KioskConsentService
from app.services.kiosk_anchor_service import KioskAnchorService
from app.services.ivr_service import IVRService
from app.services.photo_verification_service import PhotoVerificationService

load_dotenv()

SECRET_KEY = os.getenv("JWT_SECRET_KEY", os.getenv("SECRET_KEY", "fallback-secret"))
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = 8
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")

router = APIRouter()


# ── §2.7 — OTP Rate Limiter (in-memory) ──

_otp_rate_limit: dict = defaultdict(list)  # mobile -> [timestamps]
_kiosk_rate_limit: dict = defaultdict(list)  # ip -> [timestamps]
_kiosk_otp_rate_limit: dict = defaultdict(list)  # loan_id -> [timestamps]

def _check_otp_rate_limit(mobile: str):
    """Check if mobile has exceeded 3 OTP requests in 10 minutes. Raises 429 if exceeded."""
    now = time.time()
    window = 10 * 60  # 10 minutes
    # Clean up stale timestamps
    _otp_rate_limit[mobile] = [t for t in _otp_rate_limit[mobile] if now - t < window]
    if len(_otp_rate_limit[mobile]) >= 3:
        raise HTTPException(
            status_code=429,
            detail={
                "error_code": "RATE_LIMITED",
                "message": "Too many OTP requests. Please wait 10 minutes.",
            },
        )
    _otp_rate_limit[mobile].append(now)


def _check_kiosk_start_rate_limit(ip: str):
    """10 kiosk starts per hour per IP."""
    now = time.time()
    window = 3600
    _kiosk_rate_limit[ip] = [t for t in _kiosk_rate_limit[ip] if now - t < window]
    if len(_kiosk_rate_limit[ip]) >= 10:
        raise HTTPException(
            status_code=429,
            detail={"error_code": "RATE_LIMITED", "message": "Too many kiosk sessions. Wait 1 hour."},
        )
    _kiosk_rate_limit[ip].append(now)


def _check_kiosk_otp_rate_limit(loan_id: str):
    """3 OTP initiations per 30 minutes per loan."""
    now = time.time()
    window = 30 * 60
    _kiosk_otp_rate_limit[loan_id] = [t for t in _kiosk_otp_rate_limit[loan_id] if now - t < window]
    if len(_kiosk_otp_rate_limit[loan_id]) >= 3:
        raise HTTPException(
            status_code=429,
            detail={"error_code": "RATE_LIMITED", "message": "Too many OTP requests. Wait 30 minutes."},
        )
    _kiosk_otp_rate_limit[loan_id].append(now)


# ══════════════════════════════════════════════════════════════════════
#  1. LOAN ENDPOINTS
# ══════════════════════════════════════════════════════════════════════

@router.post("/loans/create", response_model=LoanResponse, tags=["Loans"])
def create_loan(
    loan_data: LoanCreate,
    db: Session = Depends(get_db),
    crypto: CryptoService = Depends(get_crypto_service),
    policy: PolicyEngine = Depends(get_policy_engine),
    sms: SMSService = Depends(get_sms_service),
    notification: NotificationService = Depends(get_notification_service),
):
    """Create a new loan application (Clerk endpoint)."""
    # Validate
    validation = policy.validate_loan(loan_data.amount, loan_data.purpose)
    if not validation["is_valid"]:
        raise HTTPException(status_code=400, detail={"violations": validation["violations"]})

    # Generate unique loan_id
    loan_id = f"LN{int(time.time() * 1000)}"

    # Determine approval tier
    tier = policy.determine_tier(loan_data.amount)

    # Compute loan hash from exact parameters
    hash_params = {
        "loan_id": loan_id,
        "farmer_id": loan_data.farmer_id,
        "farmer_name": loan_data.farmer_name,
        "amount": loan_data.amount,
        "tenure_months": loan_data.tenure_months,
        "interest_rate": loan_data.interest_rate,
        "purpose": loan_data.purpose,
    }
    loan_hash = crypto.generate_loan_hash(hash_params)

    #(Fraud Type 2)
    farmer_declared_amount = None
    if loan_data.declaration_id:
        declaration = db.query(FarmerDeclaration).filter(
            FarmerDeclaration.declaration_id == loan_data.declaration_id
        ).first()
        if not declaration:
            raise HTTPException(status_code=404, detail="Declaration not found")
        farmer_declared_amount = declaration.declared_amount
        declaration.status = "linked"

    loan = Loan(
        loan_id=loan_id,
        farmer_id=loan_data.farmer_id,
        farmer_name=loan_data.farmer_name,
        farmer_mobile=loan_data.farmer_mobile,
        amount=loan_data.amount,
        tenure_months=loan_data.tenure_months,
        interest_rate=loan_data.interest_rate,
        purpose=loan_data.purpose,
        loan_hash=loan_hash,
        status="pending_farmer_consent",
        approval_tier=tier,
        created_by=loan_data.created_by,
        declaration_id=loan_data.declaration_id,
        farmer_declared_amount=farmer_declared_amount,
        amount_difference_reason=loan_data.amount_difference_reason,
    )
    db.add(loan)
    db.commit()
    db.refresh(loan)

    try:
        notification.send_loan_creation_notification(
            db=db,
            farmer_mobile=loan_data.farmer_mobile,
            loan_details={
                "amount": loan_data.amount,
                "purpose": loan_data.purpose,
                "loan_id": loan_id,
                "branch": "DCCB Branch",
            },
        )
    except Exception as e:
        print(f"⚠ Notification sending failed: {e}")

    try:
        sms.send_loan_creation_confirmation(
            mobile=loan_data.farmer_mobile,
            loan_id=loan_id,
            amount=loan_data.amount,
            declared_amount=farmer_declared_amount,
        )
    except Exception:
        pass

    return loan


@router.get("/loans/pending-review", tags=["Clerk"])
def get_pending_review_loans(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Get loans pending clerk review (completed kiosk sessions)."""
    loans = db.query(Loan).filter(
        Loan.status == "pending_clerk_review"
    ).order_by(Loan.kiosk_completed_at.desc()).all()

    # Fetch confirmed amounts/purposes from LoanDocument
    loan_ids = [l.loan_id for l in loans]
    docs = {d.loan_id: d for d in db.query(LoanDocument).filter(LoanDocument.loan_id.in_(loan_ids)).all()} if loan_ids else {}

    return {
        "loans": [
            {
                "loan_id": l.loan_id,
                "farmer_name": l.farmer_name or l.aadhaar_verified_name,
                "farmer_confirmed_name": l.farmer_name,
                "amount": l.amount,
                "purpose": l.purpose,
                "farmer_confirmed_amount": docs[l.loan_id].farmer_confirmed_amount if l.loan_id in docs else l.amount,
                "farmer_confirmed_purpose": docs[l.loan_id].farmer_confirmed_purpose if l.loan_id in docs else l.purpose,
                "kiosk_completed_at": l.kiosk_completed_at.isoformat() if l.kiosk_completed_at else None,
                "kiosk_session_id": l.kiosk_session_id,
                "aadhaar_verified_name": l.aadhaar_verified_name,
                "document_hash": l.document_hash[:16] if l.document_hash else None,
                "kiosk_phase_anchor_hash": l.kiosk_phase_anchor_hash[:16] if l.kiosk_phase_anchor_hash else None,
                "assistance_session": l.assistance_session,
                "assisting_employee_name": l.assisting_employee_name,
                "assisting_employee_id": l.assisting_employee_id,
                "status": l.status,
            }
            for l in loans
        ],
        "total": len(loans),
    }


@router.get("/loans/{loan_id}/review-detail", tags=["Clerk"])
def get_review_detail(
    loan_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Full read-only loan record for clerk review. Records clerk_review_opened_at on first open."""
    loan = db.query(Loan).filter(Loan.loan_id == loan_id).first()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")

    presence = db.query(KioskPresenceRecord).filter(KioskPresenceRecord.loan_id == loan_id).first()
    loan_doc = db.query(LoanDocument).filter(LoanDocument.loan_id == loan_id).first()
    session = db.query(KioskSession).filter(KioskSession.loan_id == loan_id).first()

    # Record the review open time on the loan record (persisted, not in-memory)
    now = datetime.now(timezone.utc)
    if not loan.clerk_review_opened_at:
        loan.clerk_review_opened_at = now
        db.commit()

    return {
        "loan_id": loan.loan_id,
        "farmer_name": loan.farmer_name or loan.aadhaar_verified_name,
        "farmer_confirmed_name": loan.farmer_name,
        "amount": loan.amount,
        "purpose": loan.purpose,
        "status": loan.status,
        "approval_tier": loan.approval_tier,
        "loan_hash": loan.loan_hash,
        "document_hash": loan.document_hash,
        "kiosk_phase_anchor_hash": loan.kiosk_phase_anchor_hash,
        "kiosk_completed_at": loan.kiosk_completed_at.isoformat() if loan.kiosk_completed_at else None,
        "clerk_review_opened_at": loan.clerk_review_opened_at.isoformat() if loan.clerk_review_opened_at else now.isoformat(),
        "assistance_session": loan.assistance_session,
        "assisting_employee_name": loan.assisting_employee_name,
        "assisting_employee_id": loan.assisting_employee_id,
        "presence": {
            "gps_latitude": presence.gps_latitude if presence else None,
            "gps_longitude": presence.gps_longitude if presence else None,
            "gps_captured_at": presence.gps_captured_at.isoformat() if presence and presence.gps_captured_at else None,
            "photo_hash": presence.photo_hash if presence else None,
            "photo_captured_at": presence.photo_captured_at.isoformat() if presence and presence.photo_captured_at else None,
            "aadhaar_last_four": presence.aadhaar_last_four if presence else None,
            "aadhaar_verified_name": presence.aadhaar_verified_name if presence else None,
            "aadhaar_otp_verified": presence.aadhaar_otp_verified if presence else False,
            "aadhaar_verified_at": presence.aadhaar_verified_at.isoformat() if presence and presence.aadhaar_verified_at else None,
            "terms_accepted_at": presence.terms_accepted_at.isoformat() if presence and presence.terms_accepted_at else None,
            "face_detected_client_side": presence.face_detected_client_side if presence else None,
            "liveness_check_suspicious": presence.liveness_check_suspicious if presence else None,
            "device_fingerprint_hash": presence.device_fingerprint_hash if presence else None,
            "assisting_employee_name": presence.assisting_employee_name if presence else None,
            "assisting_employee_id": presence.assisting_employee_id if presence else None,
        } if presence else None,
        "document": {
            "document_hash": loan_doc.document_hash if loan_doc else None,
            "ocr_extracted_amount": loan_doc.ocr_extracted_amount if loan_doc else None,
            "ocr_extracted_purpose": loan_doc.ocr_extracted_purpose if loan_doc else None,
            "farmer_confirmed_amount": loan_doc.farmer_confirmed_amount if loan_doc else None,
            "farmer_confirmed_purpose": loan_doc.farmer_confirmed_purpose if loan_doc else None,
            "ocr_confidence_score": loan_doc.ocr_confidence_score if loan_doc else None,
            "document_uploaded_at": loan_doc.document_uploaded_at.isoformat() if loan_doc and loan_doc.document_uploaded_at else None,
            # Structured OCR fields
            "ocr_extracted_account_number": loan_doc.ocr_extracted_account_number if loan_doc else None,
            "ocr_extracted_ifsc": loan_doc.ocr_extracted_ifsc if loan_doc else None,
            "ocr_extracted_phone": loan_doc.ocr_extracted_phone if loan_doc else None,
            "ocr_extracted_aadhaar_masked": loan_doc.ocr_extracted_aadhaar_masked if loan_doc else None,
            "ocr_extracted_annual_income": loan_doc.ocr_extracted_annual_income if loan_doc else None,
            "ocr_extracted_land_ownership": loan_doc.ocr_extracted_land_ownership if loan_doc else None,
            "ocr_extracted_loan_reason": loan_doc.ocr_extracted_loan_reason if loan_doc else None,
            "ocr_engine_used": loan_doc.ocr_engine_used if loan_doc else None,
            "ocr_needs_review_fields": loan_doc.ocr_needs_review_fields.split(",") if loan_doc and loan_doc.ocr_needs_review_fields else [],
            "ocr_field_confidences": json.loads(loan_doc.ocr_field_confidences_json) if loan_doc and loan_doc.ocr_field_confidences_json else {},
            # Farmer-confirmed structured fields
            "farmer_confirmed_account_number": loan_doc.farmer_confirmed_account_number if loan_doc else None,
            "farmer_confirmed_ifsc": loan_doc.farmer_confirmed_ifsc if loan_doc else None,
            "farmer_confirmed_phone": loan_doc.farmer_confirmed_phone if loan_doc else None,
            "farmer_confirmed_annual_income": loan_doc.farmer_confirmed_annual_income if loan_doc else None,
            "farmer_confirmed_land_ownership": loan_doc.farmer_confirmed_land_ownership if loan_doc else None,
            "farmer_confirmed_loan_reason": loan_doc.farmer_confirmed_loan_reason if loan_doc else None,
        } if loan_doc else None,
        "session": {
            "session_id": session.session_id if session else None,
            "status": session.session_status if session else None,
            "ip_address": session.ip_address if session else None,
        } if session else None,
    }


@router.post("/loans/{loan_id}/clerk-accept", tags=["Clerk"])
def clerk_accept_loan(
    loan_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_roles("clerk")),
):
    """Clerk accepts a loan — transitions from pending_clerk_review to pending_approvals.
    Enforces 60-second minimum review time and records verification metadata."""
    loan = db.query(Loan).filter(Loan.loan_id == loan_id).first()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")
    if loan.status != "pending_clerk_review":
        raise HTTPException(status_code=400, detail=f"Cannot accept loan in status '{loan.status}'")

    # Enforce 60-second minimum review time
    now = datetime.now(timezone.utc)
    if loan.clerk_review_opened_at:
        opened_at = loan.clerk_review_opened_at
        if opened_at.tzinfo is None:
            opened_at = opened_at.replace(tzinfo=timezone.utc)
        elapsed = (now - opened_at).total_seconds()
        if elapsed < 60:
            raise HTTPException(
                status_code=400,
                detail=f"Minimum review time not met. Please review all sections carefully. ({int(60 - elapsed)}s remaining)"
            )
    else:
        raise HTTPException(
            status_code=400,
            detail="Review detail page was not opened. Please open and review before accepting."
        )

    loan.status = "pending_approvals"
    loan.clerk_reviewed_by = current_user["user_id"]
    loan.clerk_accepted_at = now
    loan.updated_at = now

    # Store verification metadata in metadata_json
    existing_meta = {}
    if loan.metadata_json:
        try:
            existing_meta = json.loads(loan.metadata_json) if isinstance(loan.metadata_json, str) else loan.metadata_json
        except (json.JSONDecodeError, TypeError):
            existing_meta = {}
    existing_meta["clerk_verification_complete"] = True
    existing_meta["clerk_verification_timestamp"] = now.isoformat()
    existing_meta["clerk_user_id"] = current_user["user_id"]
    loan.metadata_json = json.dumps(existing_meta)

    db.commit()

    return {
        "loan_id": loan_id,
        "status": "pending_approvals",
        "clerk_reviewed_by": current_user["user_id"],
        "accepted_at": now.isoformat(),
        "clerk_verification_complete": True,
    }


REJECTION_CATEGORIES = [
    "Incomplete Documentation",
    "Suspected Fraudulent Application",
    "Farmer Information Mismatch",
    "Duplicate Application",
    "Policy Violation",
    "Other",
]


@router.post("/loans/{loan_id}/clerk-reject", tags=["Clerk"])
def clerk_reject_loan(
    loan_id: str,
    data: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_roles("clerk")),
):
    """Clerk rejects a loan with mandatory reason and category."""
    loan = db.query(Loan).filter(Loan.loan_id == loan_id).first()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")
    if loan.status != "pending_clerk_review":
        raise HTTPException(status_code=400, detail=f"Cannot reject loan in status '{loan.status}'")

    reason_text = data.get("reason_text", "")
    rejection_category = data.get("rejection_category", "")

    if len(reason_text) < 20:
        raise HTTPException(status_code=422, detail="Rejection reason must be at least 20 characters")
    if rejection_category not in REJECTION_CATEGORIES:
        raise HTTPException(status_code=422, detail=f"Invalid rejection category. Must be one of: {REJECTION_CATEGORIES}")

    now = datetime.now(timezone.utc)
    loan.status = "clerk_rejected"
    loan.clerk_reviewed_by = current_user["user_id"]
    loan.clerk_rejected_at = now
    loan.rejection_reason = reason_text
    loan.rejection_category = rejection_category
    loan.updated_at = now
    db.commit()

    return {
        "loan_id": loan_id,
        "status": "clerk_rejected",
        "clerk_reviewed_by": current_user["user_id"],
        "rejected_at": now.isoformat(),
        "reason": reason_text,
        "category": rejection_category,
    }


@router.get("/loans/{loan_id}", response_model=LoanResponse, tags=["Loans"])
def get_loan(loan_id: str, db: Session = Depends(get_db)):
    """Get a single loan by loan_id."""
    loan = db.query(Loan).filter(Loan.loan_id == loan_id).first()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")
    return loan


@router.get("/loans", response_model=LoanListResponse, tags=["Loans"])
def list_loans(
    status: Optional[str] = Query(None),
    farmer_id: Optional[str] = Query(None),
    created_by: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """List all loans with optional filters."""
    query = db.query(Loan)
    if status:
        query = query.filter(Loan.status == status)
    if farmer_id:
        query = query.filter(Loan.farmer_id == farmer_id)
    if created_by:
        query = query.filter(Loan.created_by == created_by)

    total = query.count()
    loans = query.order_by(Loan.created_at.desc()).all()
    return LoanListResponse(loans=loans, total=total)


# ══════════════════════════════════════════════════════════════════════
#  2. FARMER CONSENT ENDPOINTS (with §2.6 idempotency + §2.8 nonce)
# ══════════════════════════════════════════════════════════════════════

@router.post(
    "/loans/{loan_id}/farmer-consent",
    response_model=FarmerConsentResponse,
    tags=["Consent"],
)
def create_farmer_consent(
    loan_id: str,
    data: FarmerConsentCreate,
    db: Session = Depends(get_db),
    consent_engine: ConsentEngine = Depends(get_consent_engine),
    notification: NotificationService = Depends(get_notification_service),
):
    """Farmer grants cryptographic consent to exact loan terms."""
    loan = db.query(Loan).filter(Loan.loan_id == loan_id).first()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")

    # §2.6 — Idempotency check
    existing_consent = db.query(FarmerConsent).filter(FarmerConsent.loan_id == loan_id).first()
    if existing_consent:
        raise HTTPException(
            status_code=409,
            detail={"error_code": "ALREADY_EXISTS", "message": "Consent already recorded for this loan"},
        )

    # §2.8 — Nonce replay protection
    existing_nonce = db.query(UsedNonce).filter(UsedNonce.nonce == data.nonce).first()
    if existing_nonce:
        raise HTTPException(
            status_code=409,
            detail={"error_code": "REPLAY_DETECTED", "message": "This consent request has already been processed"},
        )
    # Store the nonce
    db.add(UsedNonce(nonce=data.nonce, loan_id=loan_id))
    db.flush()

    try:
        consent = consent_engine.create_farmer_consent(
            db=db,
            loan=loan,
            otp=data.otp,
            device_info=data.device_info,
            ip_address=data.ip_address,
            live_photo_base64=data.live_photo_base64,
            gps_latitude=data.gps_latitude,
            gps_longitude=data.gps_longitude,
            device_fingerprint=data.device_fingerprint,
            bank_kyc_verified=data.bank_kyc_verified or False,
            otp_reference_id=data.otp_reference_id,
            fingerprint_hash=data.fingerprint_hash,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        notification.send_consent_confirmation_notification(
            db=db,
            farmer_mobile=loan.farmer_mobile,
            loan_details={
                "amount": loan.amount,
                "loan_id": loan.loan_id,
                "tenure_months": loan.tenure_months,
                "interest_rate": loan.interest_rate,
                "branch": "DCCB Branch",
                "consent_timestamp": consent.consented_at.strftime("%d-%b-%Y %I:%M %p")
                if consent.consented_at else None,
            },
        )
    except Exception as e:
        print(f"⚠ Consent notification failed: {e}")

    return consent


# ══════════════════════════════════════════════════════════════════════
#  2b. DISBURSEMENT CONSENT ENDPOINT (Fraud Type 1) — §2.6 idempotency
# ══════════════════════════════════════════════════════════════════════

@router.post(
    "/loans/{loan_id}/disbursement-consent",
    response_model=DisbursementConsentResponse,
    tags=["Fraud Prevention"],
)
def create_disbursement_consent(
    loan_id: str,
    data: DisbursementConsentCreate,
    db: Session = Depends(get_db),
    penny_drop: PennyDropService = Depends(get_penny_drop_service),
    crypto: CryptoService = Depends(get_crypto_service),
    sms: SMSService = Depends(get_sms_service),
    notification: NotificationService = Depends(get_notification_service),
):
    """Farmer verifies their bank account for disbursement (Benami fraud prevention)."""
    loan = db.query(Loan).filter(Loan.loan_id == loan_id).first()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")

    # §2.6 — Idempotency: return 409 instead of 400
    existing = db.query(DisbursementConsent).filter(
        DisbursementConsent.loan_id == loan_id
    ).first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail={"error_code": "ALREADY_EXISTS", "message": "Disbursement consent already recorded for this loan"},
        )

    verification = penny_drop.verify_account_ownership(
        account_number=data.account_number,
        ifsc_code=data.ifsc_code,
        expected_name=data.account_holder_name,
        farmer_registered_name=loan.farmer_name,
    )

    # Block consent if account holder name does not match farmer's registered name
    if not verification["name_matched"]:
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": "ACCOUNT_VERIFICATION_FAILED",
                "name_matched": False,
                "similarity_score": verification.get("similarity_score", 0),
                "message": (
                    f"Account holder name '{data.account_holder_name}' does not match "
                    f"farmer identity records. Similarity: {verification.get('similarity_score', 0)}%"
                ),
            },
        )

    disbursement_data = {
        "loan_id": loan_id,
        "account_number": data.account_number,
        "ifsc_code": data.ifsc_code,
        "account_holder_name": data.account_holder_name,
    }
    disbursement_hash = crypto.generate_loan_hash(disbursement_data)

    disbursement = DisbursementConsent(
        loan_id=loan_id,
        account_number=data.account_number,
        account_holder_name=data.account_holder_name,
        ifsc_code=data.ifsc_code,
        penny_drop_verified=verification["verified"],
        penny_drop_name_matched=verification["name_matched"],
        penny_drop_response=json.dumps(verification),
        disbursement_hash=disbursement_hash,
    )
    db.add(disbursement)
    db.commit()
    db.refresh(disbursement)

    try:
        notification.send_disbursement_notification(
            db=db,
            farmer_mobile=loan.farmer_mobile,
            loan_id=loan_id,
            account_number=data.account_number,
            amount=loan.amount,
        )
    except Exception:
        pass

    try:
        sms.send_disbursement_confirmation(
            mobile=loan.farmer_mobile,
            loan_id=loan_id,
            account_number=data.account_number,
        )
    except Exception:
        pass

    response = DisbursementConsentResponse(
        id=disbursement.id,
        loan_id=disbursement.loan_id,
        account_number=disbursement.account_number,
        account_holder_name=disbursement.account_holder_name,
        ifsc_code=disbursement.ifsc_code,
        penny_drop_verified=disbursement.penny_drop_verified,
        penny_drop_name_matched=disbursement.penny_drop_name_matched,
        bank_name=verification.get("bank_name"),
        disbursement_hash=disbursement.disbursement_hash,
        consented_at=disbursement.consented_at,
    )
    return response


# ══════════════════════════════════════════════════════════════════════
#  2c. FARMER DECLARATION ENDPOINT (Fraud Type 2)
# ══════════════════════════════════════════════════════════════════════

@router.post(
    "/farmer-declaration",
    response_model=FarmerDeclarationResponse,
    tags=["Fraud Prevention"],
)
def create_farmer_declaration(
    data: FarmerDeclarationCreate,
    db: Session = Depends(get_db),
    crypto: CryptoService = Depends(get_crypto_service),
    sms: SMSService = Depends(get_sms_service),
):
    """Farmer self-declares the loan amount they need (Amount Inflation prevention)."""
    declaration_id = f"DEC{int(time.time() * 1000)}"

    # Hash the declaration
    declaration_params = {
        "farmer_id": data.farmer_id,
        "farmer_name": data.farmer_name,
        "declared_amount": data.declared_amount,
        "purpose": data.purpose,
    }
    declaration_hash = crypto.generate_loan_hash(declaration_params)

    # Sign the declaration
    key_id = f"farmer_{data.farmer_id}"
    try:
        declaration_signature = crypto.sign_data(declaration_hash, key_id)
    except Exception:
        declaration_signature = None

    declaration = FarmerDeclaration(
        declaration_id=declaration_id,
        farmer_id=data.farmer_id,
        farmer_name=data.farmer_name,
        farmer_mobile=data.farmer_mobile,
        declared_amount=data.declared_amount,
        purpose=data.purpose,
        declaration_hash=declaration_hash,
        declaration_signature=declaration_signature,
        otp_verified=True,
        status="active",
    )
    db.add(declaration)
    db.commit()
    db.refresh(declaration)

    try:
        sms.send_declaration_confirmation(
            mobile=data.farmer_mobile,
            declaration_id=declaration_id,
            amount=data.declared_amount,
        )
    except Exception:
        pass

    return declaration


@router.get(
    "/farmer-declaration/{declaration_id}",
    response_model=FarmerDeclarationResponse,
    tags=["Fraud Prevention"],
)
def get_farmer_declaration(
    declaration_id: str,
    db: Session = Depends(get_db),
):
    """Get a farmer declaration by ID."""
    declaration = db.query(FarmerDeclaration).filter(
        FarmerDeclaration.declaration_id == declaration_id
    ).first()
    if not declaration:
        raise HTTPException(status_code=404, detail="Declaration not found")
    return declaration


# ══════════════════════════════════════════════════════════════════════
#  3. APPROVAL ENDPOINTS — §2.6 idempotency
# ══════════════════════════════════════════════════════════════════════

@router.post(
    "/loans/{loan_id}/approve",
    response_model=ApprovalResponse,
    tags=["Approvals"],
)
def create_approval(
    loan_id: str,
    data: ApprovalCreate,
    db: Session = Depends(get_db),
    consent_engine: ConsentEngine = Depends(get_consent_engine),
    policy: PolicyEngine = Depends(get_policy_engine),
):
    """Manager approves a loan with a cryptographic signature."""
    loan = db.query(Loan).filter(Loan.loan_id == loan_id).first()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")

    # §2.6 — Idempotency: check for duplicate approval by same approver
    existing = db.query(Approval).filter(
        Approval.loan_id == loan_id,
        Approval.approver_id == data.approver_id,
    ).first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail={"error_code": "ALREADY_EXISTS", "message": "Approval already recorded by this approver"},
        )

    try:
        approval = consent_engine.create_manager_approval(
            db=db,
            loan=loan,
            approver_id=data.approver_id,
            approver_name=data.approver_name,
            approver_role=data.approver_role,
            comments=data.comments,
            ip_address=data.ip_address,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    current_approvals = (
        db.query(Approval).filter(Approval.loan_id == loan_id).all()
    )
    approvals_dicts = [
        {"approver_role": a.approver_role, "approver_id": a.approver_id}
        for a in current_approvals
    ]
    missing = policy.get_missing_approvals(loan.amount, approvals_dicts)
    is_complete = len(missing) == 0

    return approval


@router.get("/loans/{loan_id}/approvals", tags=["Approvals"])
def get_approvals(
    loan_id: str,
    db: Session = Depends(get_db),
    policy: PolicyEngine = Depends(get_policy_engine),
):
    """Get all approvals for a loan and the approval status."""
    loan = db.query(Loan).filter(Loan.loan_id == loan_id).first()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")

    approvals = (
        db.query(Approval)
        .filter(Approval.loan_id == loan_id)
        .order_by(Approval.approved_at.asc())
        .all()
    )
    approvals_dicts = [
        {"approver_role": a.approver_role, "approver_id": a.approver_id}
        for a in approvals
    ]
    missing = policy.get_missing_approvals(loan.amount, approvals_dicts)
    required = policy.get_required_approvals(loan.amount)

    return {
        "loan_id": loan_id,
        "approvals": [
            {
                "id": a.id,
                "approver_id": a.approver_id,
                "approver_name": a.approver_name,
                "approver_role": a.approver_role,
                "loan_hash": a.loan_hash,
                "comments": a.comments,
                "approved_at": a.approved_at.isoformat() if a.approved_at else None,
            }
            for a in approvals
        ],
        "required_approvals": required,
        "missing_approvals": missing,
        "approvals_complete": len(missing) == 0,
        "total_approvals": len(approvals),
    }


# ══════════════════════════════════════════════════════════════════════
#  3b. MANAGER REJECTION ENDPOINT
# ══════════════════════════════════════════════════════════════════════

MANAGER_REJECTION_CATEGORIES = [
    "Credit Risk",
    "Insufficient Collateral",
    "Policy Violation",
    "Duplicate Application",
    "Suspicious Documentation",
    "Incomplete Information",
    "Exceeds Eligibility Limit",
    "Other",
]


@router.post("/loans/{loan_id}/manager-reject", tags=["Approvals"])
def manager_reject_loan(
    loan_id: str,
    data: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_roles("branch_manager", "credit_manager", "ceo", "board_member")),
    crypto: CryptoService = Depends(get_crypto_service),
    policy: PolicyEngine = Depends(get_policy_engine),
):
    """Manager rejects a loan with cryptographic Ed25519 signature.
    The rejection is permanent — a manager-rejected loan cannot be reactivated."""
    loan = db.query(Loan).filter(Loan.loan_id == loan_id).first()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")

    # Validate loan is in a rejectable status
    rejectable_statuses = ("pending_approvals", "cbs_validated", "ready_for_execution")
    if loan.status not in rejectable_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot reject loan in status '{loan.status}'. Only loans in {rejectable_statuses} can be manager-rejected."
        )

    # Validate the manager's role is a required approver for this loan's tier
    manager_role = current_user["role"]
    if not policy.is_role_required(loan.amount, manager_role):
        raise HTTPException(
            status_code=403,
            detail=f"Role '{manager_role}' is not a required approver for this loan's approval tier ({loan.approval_tier}). "
                   f"Only required approvers can reject a loan."
        )

    rejection_reason = data.get("rejection_reason", "")
    rejection_category = data.get("rejection_category", "")

    if len(rejection_reason) < 30:
        raise HTTPException(
            status_code=422,
            detail="Rejection reason must be at least 30 characters. Managers must provide a substantive reason."
        )
    if rejection_category not in MANAGER_REJECTION_CATEGORIES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid rejection category. Must be one of: {MANAGER_REJECTION_CATEGORIES}"
        )

    # Sign the rejection with the manager's Ed25519 private key over the loan_hash
    key_id = f"approver_{current_user['user_id']}"
    rejection_signature = crypto.sign_data(loan.loan_hash, key_id)

    now = datetime.now(timezone.utc)
    loan.status = "manager_rejected"
    loan.manager_rejected_by = current_user["user_id"]
    loan.manager_rejected_by_name = current_user["name"]
    loan.manager_rejected_by_role = manager_role
    loan.manager_rejection_reason = rejection_reason
    loan.manager_rejection_category = rejection_category
    loan.manager_rejected_at = now
    loan.manager_rejection_signature = rejection_signature
    loan.updated_at = now
    db.commit()

    return {
        "loan_id": loan_id,
        "status": "manager_rejected",
        "rejected_by": current_user["user_id"],
        "rejected_by_name": current_user["name"],
        "rejected_by_role": manager_role,
        "rejection_reason": rejection_reason,
        "rejection_category": rejection_category,
        "rejected_at": now.isoformat(),
        "rejection_signature": rejection_signature[:32] + "...",
        "message": "Loan application rejected. The rejection has been cryptographically signed and recorded.",
    }


# ══════════════════════════════════════════════════════════════════════
#  3c. DISBURSEMENT-LEVEL REJECTION ENDPOINT
# ══════════════════════════════════════════════════════════════════════

DISBURSEMENT_REJECTION_CATEGORIES = [
    "Account Verification Failure",
    "Suspicious Beneficiary Account",
    "Regulatory Compliance Issue",
    "Fraud Alert Triggered",
    "CBS Validation Concern",
    "Document Irregularity Discovered",
    "Other",
]


@router.post("/loans/{loan_id}/disbursement-reject", tags=["Approvals"])
def disbursement_reject_loan(
    loan_id: str,
    data: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_roles("branch_manager", "credit_manager", "ceo", "board_member")),
    crypto: CryptoService = Depends(get_crypto_service),
    sms: SMSService = Depends(get_sms_service),
):
    """Reject a loan at the disbursement/execution stage.
    Only loans in 'cbs_validated' or 'ready_for_execution' can be rejected here.
    The rejection is cryptographically signed and permanent."""
    loan = db.query(Loan).filter(Loan.loan_id == loan_id).first()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")

    allowed = ("cbs_validated", "ready_for_execution")
    if loan.status not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot disbursement-reject loan in status '{loan.status}'. "
                   f"Only loans in {allowed} can be rejected at the disbursement stage."
        )

    rejection_reason = data.get("rejection_reason", "")
    rejection_category = data.get("rejection_category", "")

    if len(rejection_reason) < 30:
        raise HTTPException(
            status_code=422,
            detail="Rejection reason must be at least 30 characters."
        )
    if rejection_category not in DISBURSEMENT_REJECTION_CATEGORIES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid category. Must be one of: {DISBURSEMENT_REJECTION_CATEGORIES}"
        )

    # Sign the rejection with the manager's Ed25519 private key
    key_id = f"approver_{current_user['user_id']}"
    rejection_signature = crypto.sign_data(loan.loan_hash, key_id)

    now = datetime.now(timezone.utc)
    loan.status = "disbursement_rejected"
    loan.manager_rejected_by = current_user["user_id"]
    loan.manager_rejected_by_name = current_user["name"]
    loan.manager_rejected_by_role = current_user["role"]
    loan.manager_rejection_reason = rejection_reason
    loan.manager_rejection_category = rejection_category
    loan.manager_rejected_at = now
    loan.manager_rejection_signature = rejection_signature
    loan.updated_at = now
    db.commit()

    # Send SMS notification to farmer
    try:
        sms.send_sms(
            mobile=loan.farmer_mobile,
            message=(
                f"IMPORTANT: Your loan application {loan.loan_id} for "
                f"Rs.{loan.amount:,.0f} has been REJECTED at the disbursement stage. "
                f"Reason: {rejection_category}. "
                f"Please contact your bank branch for details."
            ),
        )
    except Exception:
        pass

    return {
        "loan_id": loan_id,
        "status": "disbursement_rejected",
        "rejected_by": current_user["user_id"],
        "rejected_by_name": current_user["name"],
        "rejected_by_role": current_user["role"],
        "rejection_reason": rejection_reason,
        "rejection_category": rejection_category,
        "rejected_at": now.isoformat(),
        "rejection_signature": rejection_signature[:32] + "...",
        "message": "Loan rejected at disbursement stage. The rejection has been cryptographically signed and recorded.",
    }


# ══════════════════════════════════════════════════════════════════════
#  4. EXECUTION ENDPOINT
# ══════════════════════════════════════════════════════════════════════

@router.post("/execute-loan", tags=["Execution"])
def execute_loan(
    loan_id: str = Query(...),
    db: Session = Depends(get_db),
    consent_engine: ConsentEngine = Depends(get_consent_engine),
    blockchain: BlockchainService = Depends(get_blockchain_service),
    notification: NotificationService = Depends(get_notification_service),
):
    """Validate and execute a loan, anchoring proof on blockchain."""
    is_eligible, final_token, error = consent_engine.validate_execution_eligibility(
        db, loan_id
    )

    if not is_eligible:
        raise HTTPException(status_code=400, detail=error)

    # Update loan status
    loan = db.query(Loan).filter(Loan.loan_id == loan_id).first()
    loan.status = "executed"
    loan.updated_at = datetime.now(timezone.utc)
    db.commit()

    # Anchor on blockchain (database-backed chain)
    anchor = blockchain.anchor_consent(db, loan_id, final_token)

    loan.status = "anchored"
    loan.updated_at = datetime.now(timezone.utc)
    db.commit()

    # Send disbursement SMS notification to farmer
    disbursement_notif = None
    try:
        disbursement = db.query(DisbursementConsent).filter(
            DisbursementConsent.loan_id == loan_id
        ).first()
        farmer_mobile = loan.farmer_mobile or "0000000000"
        account_number = disbursement.account_number if disbursement else "XXXXXXXX"

        disbursement_notif = notification.send_disbursement_notification(
            db=db,
            farmer_mobile=farmer_mobile,
            loan_id=loan_id,
            account_number=account_number,
            amount=loan.amount,
        )
    except Exception as e:
        print(f"⚠ Disbursement notification failed: {e}")

    return {
        "execution_authorized": True,
        "loan_id": loan_id,
        "final_consent_token": final_token,
        "blockchain_anchor": {
            "block_number": anchor.block_number,
            "transaction_hash": anchor.transaction_hash,
            "consent_hash": anchor.consent_hash,
            "anchored_at": anchor.anchored_at.isoformat() if anchor.anchored_at else None,
        },
        "disbursement_notification": {
            "sent": disbursement_notif is not None,
            "delivery_status": disbursement_notif.delivery_status if disbursement_notif else None,
        },
    }


# ══════════════════════════════════════════════════════════════════════
#  5. AUDIT ENDPOINTS
# ══════════════════════════════════════════════════════════════════════

@router.get("/audit/{loan_id}", tags=["Audit"])
def audit_loan(
    loan_id: str,
    db: Session = Depends(get_db),
    crypto: CryptoService = Depends(get_crypto_service),
    policy: PolicyEngine = Depends(get_policy_engine),
    blockchain: BlockchainService = Depends(get_blockchain_service),
):
    """Comprehensive audit verification of a loan."""
    loan = db.query(Loan).filter(Loan.loan_id == loan_id).first()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")

    checks = []

    # 1. Recompute loan hash
    loan_params = {
        "loan_id": loan.loan_id,
        "farmer_id": loan.farmer_id,
        "farmer_name": loan.farmer_name,
        "amount": loan.amount,
        "tenure_months": loan.tenure_months,
        "interest_rate": loan.interest_rate,
        "purpose": loan.purpose,
    }
    recomputed_hash = crypto.generate_loan_hash(loan_params)
    hash_match = recomputed_hash == loan.loan_hash
    checks.append({
        "check": "Hash Integrity",
        "status": "valid" if hash_match else "invalid",
        "detail": f"Stored: {loan.loan_hash}, Recomputed: {recomputed_hash}",
    })

    # 2. Verify farmer consent
    consent = db.query(FarmerConsent).filter(FarmerConsent.loan_id == loan_id).first()
    if consent:
        checks.append({
            "check": "Farmer Identity Verification",
            "status": "valid" if consent.bank_kyc_verified or consent.otp_verified else "pending",
            "detail": {
                "bank_kyc_verified": consent.bank_kyc_verified or False,
                "otp_verified": consent.otp_verified is not None,
                "fingerprint_captured": consent.fingerprint_hash is not None,
                "consent_method": consent.consent_method,
            },
        })
    else:
        checks.append({
            "check": "Farmer Identity Verification",
            "status": "missing",
            "detail": "No farmer consent found",
        })
        farmer_sig_valid = False

    # 3. Verify manager approvals
    approvals = db.query(Approval).filter(Approval.loan_id == loan_id).all()
    for appr in approvals:
        approver_key_id = f"approver_{appr.approver_id}"
        sig_valid = crypto.verify_signature(
            loan.loan_hash, appr.approver_signature, approver_key_id
        )
        checks.append({
            "check": f"{appr.approver_role.replace('_', ' ').title()} Signature",
            "status": "valid" if sig_valid else "invalid",
            "detail": f"{appr.approver_name} ({appr.approver_id})",
        })

    # 4. Policy compliance
    approvals_dicts = [
        {"approver_role": a.approver_role, "approver_id": a.approver_id}
        for a in approvals
    ]
    is_compliant, compliance_msg = policy.validate_approvals(loan.amount, approvals_dicts)
    checks.append({
        "check": "Policy Compliance",
        "status": "valid" if is_compliant else "invalid",
        "detail": compliance_msg,
    })

    # 5. Notification verification
    notifications = db.query(Notification).filter(Notification.loan_id == loan_id).all()
    notif_types = {n.notification_type: n.delivery_status for n in notifications}
    all_notified = "loan_creation" in notif_types
    checks.append({
        "check": "Farmer Notifications",
        "status": "valid" if all_notified else "missing",
        "detail": {
            "loan_creation": notif_types.get("loan_creation", "not_sent"),
            "disbursement": notif_types.get("disbursement", "not_sent"),
        },
    })

    # 6. Blockchain verification (DB-backed chain)
    anchor = db.query(BlockchainAnchor).filter(BlockchainAnchor.loan_id == loan_id).first()
    blockchain_status = "not_anchored"
    blockchain_detail = {}
    if anchor:
        try:
            verify_result = blockchain.verify_loan_anchor(db, loan_id)
            blockchain_status = "valid" if verify_result.get("verified") else "invalid"
            blockchain_detail = verify_result
        except Exception as e:
            blockchain_status = "error"
            blockchain_detail = {"error": str(e)}

    checks.append({
        "check": "Blockchain Anchor",
        "status": blockchain_status,
        "detail": blockchain_detail,
    })

    # 7. Manager rejection signature verification (if applicable)
    manager_rejection_info = None
    if loan.manager_rejected_by and loan.manager_rejection_signature:
        rejector_key_id = f"approver_{loan.manager_rejected_by}"
        rejection_sig_valid = crypto.verify_signature(
            loan.loan_hash, loan.manager_rejection_signature, rejector_key_id
        )
        checks.append({
            "check": "Manager Rejection Signature",
            "status": "valid" if rejection_sig_valid else "invalid",
            "detail": f"{'✓ Rejection signature valid' if rejection_sig_valid else '✗ Rejection signature invalid'} — {loan.manager_rejected_by_name} ({loan.manager_rejected_by_role})",
        })
        manager_rejection_info = {
            "rejected_by": loan.manager_rejected_by,
            "rejected_by_name": loan.manager_rejected_by_name,
            "rejected_by_role": loan.manager_rejected_by_role,
            "rejection_reason": loan.manager_rejection_reason,
            "rejection_category": loan.manager_rejection_category,
            "rejected_at": loan.manager_rejected_at.isoformat() if loan.manager_rejected_at else None,
            "signature_valid": rejection_sig_valid,
        }

    # Overall result
    all_valid = all(c["status"] == "valid" for c in checks)
    overall = "AUTHENTIC" if all_valid else "TAMPERED"

    response = {
        "loan_id": loan_id,
        "overall_status": overall,
        "loan": {
            "farmer_name": loan.farmer_name,
            "farmer_id": loan.farmer_id,
            "amount": loan.amount,
            "tenure_months": loan.tenure_months,
            "interest_rate": loan.interest_rate,
            "purpose": loan.purpose,
            "loan_hash": loan.loan_hash,
            "status": loan.status,
            "approval_tier": loan.approval_tier,
        },
        "checks": checks,
        "verified_at": datetime.now(timezone.utc).isoformat(),
    }
    if manager_rejection_info:
        response["manager_rejection"] = manager_rejection_info
    return response


# ══════════════════════════════════════════════════════════════════════
#  6. BLOCKCHAIN ENDPOINTS (§3.5 — DB-backed chain)
# ══════════════════════════════════════════════════════════════════════

@router.get("/blockchain/chain", tags=["Blockchain"])
def get_blockchain_chain(
    blockchain: BlockchainService = Depends(get_blockchain_service),
):
    """Return the full blockchain."""
    chain = blockchain.get_full_chain()
    return {"chain": chain, "length": len(chain)}


@router.get("/blockchain/verify", tags=["Blockchain"])
def verify_blockchain(
    db: Session = Depends(get_db),
    blockchain: BlockchainService = Depends(get_blockchain_service),
):
    """Verify the integrity of the entire blockchain (§3.5)."""
    return blockchain.verify_full_chain(db)


@router.get("/blockchain/verify-loan/{loan_id}", tags=["Blockchain"])
def verify_loan_blockchain(
    loan_id: str,
    db: Session = Depends(get_db),
    blockchain: BlockchainService = Depends(get_blockchain_service),
):
    """Verify a specific loan's blockchain anchor (§3.5)."""
    return blockchain.verify_loan_anchor(db, loan_id)


# ══════════════════════════════════════════════════════════════════════
#  7. POLICY ENDPOINT
# ══════════════════════════════════════════════════════════════════════

@router.get("/policy/tier-info", tags=["Policy"])
def get_tier_info(
    amount: float = Query(..., gt=0),
    policy: PolicyEngine = Depends(get_policy_engine),
):
    """Get approval tier info for a given loan amount."""
    try:
        info = policy.get_tier_info(amount)
        return info
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ══════════════════════════════════════════════════════════════════════
#  8. AUTHENTICATION ENDPOINTS (§2.1 bcrypt + §2.2 JWT)
# ══════════════════════════════════════════════════════════════════════

from app.schemas.auth_schemas import LoginRequest, LoginResponse


@router.post("/auth/login", response_model=LoginResponse, tags=["Auth"])
def login(req: LoginRequest, db: Session = Depends(get_db)):
    """Authenticate a user by user_id and password. Returns HS256 JWT."""
    user = db.query(User).filter(User.user_id == req.user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="Invalid user ID or password")

    # §2.1 — bcrypt password verification
    if not bcrypt_hash.verify(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid user ID or password")

    # §2.2 — Generate HS256 JWT
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user.user_id,
        "name": user.name,
        "role": user.role,
        "iat": now,
        "exp": now + timedelta(hours=JWT_EXPIRY_HOURS),
    }
    token = jwt.encode(payload, SECRET_KEY, algorithm=JWT_ALGORITHM)

    return LoginResponse(
        user_id=user.user_id,
        name=user.name,
        role=user.role,
        token=token,
    )


@router.get("/auth/me", tags=["Auth"])
async def get_me(current_user: dict = Depends(get_current_user)):
    """Verify JWT token and return current user info (§2.2)."""
    return current_user


# ══════════════════════════════════════════════════════════════════════
#  9. IDENTITY VERIFICATION ENDPOINTS (§2.7 OTP rate limiting)
# ══════════════════════════════════════════════════════════════════════

@router.post("/identity/verify", tags=["Identity"])
def verify_farmer_identity(
    farmer_id: str = Query(...),
    mobile: str = Query(...),
    identity: IdentityService = Depends(get_identity_service),
):
    """Verify farmer identity via bank KYC database."""
    result = identity.verify_farmer_identity(farmer_id, mobile)
    if not result["identity_verified"]:
        raise HTTPException(status_code=400, detail=result.get("error", "Verification failed"))
    return result


@router.post("/identity/send-otp", tags=["Identity"])
def send_otp(
    mobile: str = Query(...),
    identity: IdentityService = Depends(get_identity_service),
):
    """Send OTP to farmer's registered mobile (§2.7 rate-limited)."""
    _check_otp_rate_limit(mobile)
    return identity.send_consent_otp(mobile)


@router.post("/identity/verify-otp", tags=["Identity"])
def verify_otp(
    mobile: str = Query(...),
    otp: str = Query(...),
    otp_reference_id: str = Query(...),
    identity: IdentityService = Depends(get_identity_service),
):
    """Verify OTP entered by farmer."""
    result = identity.verify_consent_otp(mobile, otp, otp_reference_id)
    if not result["verification_success"]:
        raise HTTPException(status_code=400, detail=result.get("error", "OTP verification failed"))
    return result


@router.post("/identity/capture-biometric", tags=["Device Verification"])
def capture_biometric(
    farmer_id: str = Query(...),
    device_fingerprint_hash: str = Query(""),
    webgl_renderer: str = Query(""),
    screen_resolution: str = Query(""),
    identity: IdentityService = Depends(get_identity_service),
):
    """Verify device fingerprint (Canvas + WebGL + Screen hash) for presence verification."""
    device_metadata = {
        "webgl_renderer": webgl_renderer,
        "screen_resolution": screen_resolution,
    }
    return identity.verify_device_fingerprint(
        farmer_id=farmer_id,
        device_fingerprint_hash=device_fingerprint_hash,
        device_metadata=device_metadata,
    )


# ══════════════════════════════════════════════════════════════════════
#  10. NOTIFICATION ENDPOINTS
# ══════════════════════════════════════════════════════════════════════

@router.get("/loans/{loan_id}/notifications", tags=["Notifications"])
def get_loan_notifications(
    loan_id: str,
    db: Session = Depends(get_db),
    notification: NotificationService = Depends(get_notification_service),
):
    """Get all notifications sent for a loan (audit trail)."""
    loan = db.query(Loan).filter(Loan.loan_id == loan_id).first()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")

    notifications = notification.get_notifications_for_loan(db, loan_id)

    return {
        "loan_id": loan_id,
        "notifications": [
            {
                "id": n.id,
                "notification_type": n.notification_type,
                "recipient_mobile": n.recipient_mobile,
                "sms_content": n.sms_content,
                "sent_at": n.sent_at.isoformat() if n.sent_at else None,
                "delivery_status": n.delivery_status,
            }
            for n in notifications
        ],
        "verification": notification.verify_notifications_sent(db, loan_id),
    }


# ══════════════════════════════════════════════════════════════════════
#  11. CBS VALIDATION ENDPOINT (§3.1)
# ══════════════════════════════════════════════════════════════════════

@router.post("/cbs/validate-loan/{loan_id}", tags=["CBS"])
async def validate_loan_cbs(
    loan_id: str,
    db: Session = Depends(get_db),
):
    """Run CBS (Core Banking System) validation for a loan (§3.1)."""
    loan = db.query(Loan).filter(Loan.loan_id == loan_id).first()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")

    cbs = CBSService()
    try:
        result = await cbs.validate(db, loan_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Store CBS_REF_ID in loan metadata
    existing_meta = {}
    if loan.metadata_json:
        try:
            existing_meta = json.loads(loan.metadata_json) if isinstance(loan.metadata_json, str) else loan.metadata_json
        except (json.JSONDecodeError, TypeError):
            existing_meta = {}

    existing_meta["CBS_REF_ID"] = result["CBS_REF_ID"]
    existing_meta["CBS_ELIGIBILITY"] = result["ELIGIBILITY_STATUS"]
    existing_meta["CBS_NPA_FLAG"] = result["NPA_FLAG"]
    loan.metadata_json = json.dumps(existing_meta)
    loan.cbs_validated_at = datetime.now(timezone.utc)
    db.commit()

    return result


# ══════════════════════════════════════════════════════════════════════
#  12. REGULATORY DASHBOARD ENDPOINT (§3.2)
# ══════════════════════════════════════════════════════════════════════

@router.get("/dashboard/stats", tags=["Dashboard"])
def get_dashboard_stats(
    db: Session = Depends(get_db),
    blockchain: BlockchainService = Depends(get_blockchain_service),
):
    """Regulatory dashboard statistics (§3.2). Access: auditor, board_member, ceo."""
    # Loans by status
    status_counts = dict(
        db.query(Loan.status, sql_func.count(Loan.id))
        .group_by(Loan.status)
        .all()
    )

    # Fraud attempts by type
    # Type 2: amount mismatch
    type2_fraud = db.query(Loan).filter(
        Loan.amount_difference_reason.isnot(None)
    ).count()

    # Type 1: penny-drop name mismatch
    type1_fraud = db.query(DisbursementConsent).filter(
        DisbursementConsent.penny_drop_name_matched == False
    ).count()

    # Type 3: forgery detection (loans with live photo evidence)
    type3_count = db.query(FarmerConsent).filter(
        FarmerConsent.live_photo_hash.isnot(None)
    ).count()

    # Blockchain chain integrity
    chain_integrity = blockchain.verify_full_chain(db)

    # Override events
    override_count = db.query(OverrideRequest).count()

    # Average loan lifecycle duration (for anchored loans)
    anchored_loans = db.query(Loan).filter(Loan.status == "anchored").all()
    avg_lifecycle = None
    if anchored_loans:
        durations = []
        for l in anchored_loans:
            if l.updated_at and l.created_at:
                durations.append((l.updated_at - l.created_at).total_seconds() / 3600)
        avg_lifecycle = sum(durations) / len(durations) if durations else None

    # Tier distribution
    tier_dist = dict(
        db.query(Loan.approval_tier, sql_func.count(Loan.id))
        .group_by(Loan.approval_tier)
        .all()
    )

    total_loans = db.query(Loan).count()

    # Kiosk session statistics
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    kiosk_started_today = db.query(KioskSession).filter(
        KioskSession.session_started_at >= today_start
    ).count()
    kiosk_completed_today = db.query(KioskSession).filter(
        KioskSession.session_completed_at >= today_start,
        KioskSession.session_status == "completed",
    ).count()
    kiosk_expired_today = db.query(KioskSession).filter(
        KioskSession.session_status == "expired",
    ).count()

    # Average session duration (completed sessions)
    completed_sessions = db.query(KioskSession).filter(
        KioskSession.session_status == "completed",
        KioskSession.session_completed_at.isnot(None),
    ).all()
    avg_session_duration = None
    if completed_sessions:
        durations = [
            (s.session_completed_at - s.session_started_at).total_seconds() / 60
            for s in completed_sessions
            if s.session_started_at and s.session_completed_at
        ]
        avg_session_duration = round(sum(durations) / len(durations), 1) if durations else None

    # Assistance sessions count
    assistance_count = db.query(LoanDocument).filter(
        LoanDocument.employee_assistance_used == True
    ).count()

    # Aadhaar verification success rate
    total_presence = db.query(KioskPresenceRecord).count()
    aadhaar_verified = db.query(KioskPresenceRecord).filter(
        KioskPresenceRecord.aadhaar_otp_verified == True
    ).count()
    aadhaar_success_rate = round((aadhaar_verified / total_presence * 100), 1) if total_presence > 0 else 0

    # OCR retry rate
    total_docs = db.query(LoanDocument).filter(LoanDocument.ocr_confirmed_at.isnot(None)).count()
    retried_docs = db.query(LoanDocument).filter(
        LoanDocument.ocr_confirmed_at.isnot(None),
        LoanDocument.ocr_confirmation_attempts > 1,
    ).count()
    ocr_retry_rate = round((retried_docs / total_docs * 100), 1) if total_docs > 0 else 0

    return {
        "total_loans": total_loans,
        "loans_by_status": status_counts,
        "fraud_detection": {
            "type_1_benami": type1_fraud,
            "type_2_amount_inflation": type2_fraud,
            "type_3_forgery_prevention": type3_count,
            "total_fraud_alerts": type1_fraud + type2_fraud,
        },
        "blockchain_integrity": chain_integrity,
        "override_events": override_count,
        "avg_lifecycle_hours": round(avg_lifecycle, 2) if avg_lifecycle else None,
        "tier_distribution": tier_dist,
        "kiosk_operations": {
            "sessions_started_today": kiosk_started_today,
            "sessions_completed_today": kiosk_completed_today,
            "sessions_expired": kiosk_expired_today,
            "avg_session_duration_minutes": avg_session_duration,
            "assistance_sessions": assistance_count,
            "aadhaar_verification_success_rate": aadhaar_success_rate,
            "ocr_confirmation_retry_rate": ocr_retry_rate,
        },
        # Manager rejection statistics
        "manager_rejections": {
            "manager_rejected_today": db.query(Loan).filter(
                Loan.status == "manager_rejected",
                Loan.manager_rejected_at >= today_start,
            ).count(),
            "by_category": dict(
                db.query(Loan.manager_rejection_category, sql_func.count(Loan.id))
                .filter(Loan.manager_rejection_category.isnot(None))
                .group_by(Loan.manager_rejection_category)
                .all()
            ),
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


# ══════════════════════════════════════════════════════════════════════
#  13. OVERRIDE GOVERNANCE ENDPOINTS (§3.3)
# ══════════════════════════════════════════════════════════════════════

@router.post("/loans/{loan_id}/override", tags=["Override"])
def create_override(
    loan_id: str,
    reason: str = Query(..., min_length=10),
    current_user: dict = Depends(require_roles("ceo")),
    db: Session = Depends(get_db),
):
    """CEO creates an override request for a blocked loan (§3.3)."""
    override_svc = OverrideService()
    try:
        override = override_svc.create_override_request(
            db=db,
            loan_id=loan_id,
            ceo_user_id=current_user["user_id"],
            reason_text=reason,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "id": override.id,
        "loan_id": override.loan_id,
        "requested_by": override.requested_by,
        "status": override.status,
        "reason": override.reason_text,
        "created_at": override.created_at.isoformat() if override.created_at else None,
    }


@router.post("/loans/{loan_id}/override/cosign", tags=["Override"])
def cosign_override(
    loan_id: str,
    current_user: dict = Depends(require_roles("auditor")),
    db: Session = Depends(get_db),
):
    """Auditor co-signs an override request (§3.3)."""
    override_svc = OverrideService()
    try:
        override = override_svc.cosign_override(
            db=db,
            loan_id=loan_id,
            auditor_user_id=current_user["user_id"],
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "id": override.id,
        "loan_id": override.loan_id,
        "requested_by": override.requested_by,
        "co_signed_by": override.co_signed_by,
        "status": override.status,
        "anchor_block_id": override.anchor_block_id,
    }


@router.get("/loans/{loan_id}/overrides", tags=["Override"])
def get_overrides(
    loan_id: str,
    db: Session = Depends(get_db),
):
    """Get all override requests for a loan."""
    overrides = db.query(OverrideRequest).filter(
        OverrideRequest.loan_id == loan_id
    ).all()
    return {
        "loan_id": loan_id,
        "overrides": [
            {
                "id": o.id,
                "requested_by": o.requested_by,
                "co_signed_by": o.co_signed_by,
                "status": o.status,
                "reason": o.reason_text,
                "created_at": o.created_at.isoformat() if o.created_at else None,
            }
            for o in overrides
        ],
    }


# ══════════════════════════════════════════════════════════════════════
#  14. CONSENT CERTIFICATE ENDPOINT (§3.4)
# ══════════════════════════════════════════════════════════════════════

@router.get("/loans/{loan_id}/consent-certificate", tags=["Certificate"])
def get_consent_certificate(
    loan_id: str,
    db: Session = Depends(get_db),
):
    """Generate a Digital Consent Certificate aggregating all cryptographic events (§3.4)."""
    loan = db.query(Loan).filter(Loan.loan_id == loan_id).first()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")

    # Gather all events
    consent = db.query(FarmerConsent).filter(FarmerConsent.loan_id == loan_id).first()
    approvals = db.query(Approval).filter(Approval.loan_id == loan_id).all()
    anchor = db.query(BlockchainAnchor).filter(BlockchainAnchor.loan_id == loan_id).first()
    declaration = None
    if loan.declaration_id:
        declaration = db.query(FarmerDeclaration).filter(
            FarmerDeclaration.declaration_id == loan.declaration_id
        ).first()

    # CBS validation info from metadata
    cbs_info = None
    if loan.metadata_json:
        try:
            meta = json.loads(loan.metadata_json) if isinstance(loan.metadata_json, str) else loan.metadata_json
            if "CBS_REF_ID" in meta:
                cbs_info = {
                    "CBS_REF_ID": meta.get("CBS_REF_ID"),
                    "ELIGIBILITY_STATUS": meta.get("CBS_ELIGIBILITY"),
                }
        except (json.JSONDecodeError, TypeError):
            pass

    certificate = {
        "certificate_title": "Digital Consent Certificate",
        "loan_metadata": {
            "loan_id": loan.loan_id,
            "farmer_name": loan.farmer_name,
            "farmer_id": loan.farmer_id,
            "amount": loan.amount,
            "tenure_months": loan.tenure_months,
            "interest_rate": loan.interest_rate,
            "purpose": loan.purpose,
            "loan_hash": loan.loan_hash,
            "status": loan.status,
            "created_at": loan.created_at.isoformat() if loan.created_at else None,
        },
        "declaration_event": {
            "declaration_id": declaration.declaration_id if declaration else None,
            "declared_amount": declaration.declared_amount if declaration else None,
            "declaration_hash": declaration.declaration_hash if declaration else None,
            "declaration_signature": declaration.declaration_signature if declaration else None,
        } if declaration else None,
        "consent_event": {
            "consent_token": consent.consent_token if consent else None,
            "consent_method": consent.consent_method if consent else None,
            "live_photo_hash": consent.live_photo_hash if consent else None,
            "gps_latitude": consent.gps_latitude if consent else None,
            "gps_longitude": consent.gps_longitude if consent else None,
            "consented_at": consent.consented_at.isoformat() if consent and consent.consented_at else None,
        } if consent else None,
        "approval_events": [
            {
                "approver_id": a.approver_id,
                "approver_name": a.approver_name,
                "approver_role": a.approver_role,
                "approver_signature": a.approver_signature,
                "approved_at": a.approved_at.isoformat() if a.approved_at else None,
            }
            for a in approvals
        ],
        "cbs_validation": cbs_info,
        "blockchain_anchor": {
            "block_number": anchor.block_number if anchor else None,
            "transaction_hash": anchor.transaction_hash if anchor else None,
            "consent_hash": anchor.consent_hash if anchor else None,
            "anchored_at": anchor.anchored_at.isoformat() if anchor and anchor.anchored_at else None,
        } if anchor else None,
        "audit_url": f"{BASE_URL}/api/audit/{loan_id}",
    }

    # Compute certificate hash
    cert_str = json.dumps(certificate, sort_keys=True, separators=(",", ":"), default=str)
    certificate["certificate_hash"] = hashlib.sha256(cert_str.encode()).hexdigest()
    certificate["generated_at"] = datetime.now(timezone.utc).isoformat()

    return certificate


# ══════════════════════════════════════════════════════════════════════
#  KIOSK PHASE ENDPOINTS (session token authentication)
# ══════════════════════════════════════════════════════════════════════

@router.post("/kiosk/start", tags=["Kiosk"])
def kiosk_start(
    request: Request,
    data: dict = Body(...),
    db: Session = Depends(get_db),
    service: KioskSessionService = Depends(get_kiosk_session_service),
):
    """Start a new kiosk session with a mandatory assisting employee.
    Returns session token for all subsequent requests. Rate limited: 10/hour/IP."""
    ip_address = request.client.host if request.client else "127.0.0.1"
    _check_kiosk_start_rate_limit(ip_address)

    employee_name = (data.get("employee_name") or "").strip()
    employee_id = (data.get("employee_id") or "").strip()
    if not employee_name or not employee_id:
        raise HTTPException(
            status_code=422,
            detail="Both employee_name and employee_id are required to start a kiosk session",
        )

    try:
        result = service.create_session(
            db, ip_address=ip_address,
            employee_name=employee_name, employee_id=employee_id,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/kiosk/{loan_id}/terms/accept", tags=["Kiosk"])
def kiosk_accept_terms(
    loan_id: str,
    data: dict = Body(...),
    db: Session = Depends(get_db),
    x_session_token: Optional[str] = Header(None),
):
    """Accept terms and conditions. Requires scroll_completed."""
    # Validate session
    service = KioskSessionService()
    try:
        service.validate_session_token(db, loan_id, x_session_token)
        service.update_activity(db, loan_id)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))

    scroll_completed = data.get("scroll_completed", False)
    if not scroll_completed:
        raise HTTPException(status_code=400, detail="Must scroll through all terms before accepting")

    # Update presence record
    presence = db.query(KioskPresenceRecord).filter(KioskPresenceRecord.loan_id == loan_id).first()
    if not presence:
        presence = KioskPresenceRecord(loan_id=loan_id)
        db.add(presence)
    presence.terms_accepted_at = datetime.now(timezone.utc)
    presence.terms_scroll_completed = True
    db.commit()

    return {"accepted": True, "accepted_at": presence.terms_accepted_at.isoformat()}


@router.post("/kiosk/{loan_id}/presence/photo", tags=["Kiosk"])
async def kiosk_capture_photo(
    loan_id: str,
    frame_1: UploadFile = File(...),
    frame_2: UploadFile = File(...),
    frame_3: UploadFile = File(...),
    frame_4: Optional[UploadFile] = File(None),
    frame_5: Optional[UploadFile] = File(None),
    gps_latitude: float = Form(...),
    gps_longitude: float = Form(...),
    device_fingerprint: str = Form(...),
    face_detected_client_side: bool = Form(False),
    liveness_challenges_json: str = Form("{}"),
    face_count_client: int = Form(1),
    face_centered: bool = Form(False),
    auto_captured: bool = Form(False),
    db: Session = Depends(get_db),
    x_session_token: Optional[str] = Header(None),
):
    """Capture live photo (3-5 frames) and GPS for physical presence evidence.
    Server-side validates image quality, checks liveness via frame variance,
    validates active liveness challenges, encrypts and stores photos,
    and records server-authoritative timestamp.
    Employee data is read from the loan (assigned at session start)."""
    service = KioskSessionService()
    try:
        service.validate_session_token(db, loan_id, x_session_token)
        service.update_activity(db, loan_id)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))

    photo_svc = PhotoVerificationService()

    # Read all frames (3 required + 2 optional for active liveness)
    frame_files = [frame_1, frame_2, frame_3]
    if frame_4:
        frame_files.append(frame_4)
    if frame_5:
        frame_files.append(frame_5)

    frame_bytes = []
    for i, frame_file in enumerate(frame_files, 1):
        data = await frame_file.read()
        if len(data) == 0:
            if i <= 3:  # First 3 are required
                raise HTTPException(status_code=400, detail=f"Frame {i} is empty")
            continue  # Optional frames can be empty
        # Validate image quality (Problem 1)
        result = photo_svc.validate_image_quality(data)
        if not result["valid"]:
            raise HTTPException(
                status_code=400,
                detail=f"Frame {i} failed validation: {result['error_code']} — {result['detail']}"
            )
        frame_bytes.append(data)

    if len(frame_bytes) < 3:
        raise HTTPException(status_code=400, detail="At least 3 valid frames are required")

    # Server-authoritative timestamp (Problem 5)
    now = datetime.now(timezone.utc)

    # Compute combined photo hash (Problem 2)
    photo_hash = photo_svc.compute_photo_hash(frame_bytes)

    # Parse liveness challenge data
    try:
        challenge_data = json.loads(liveness_challenges_json)
    except (json.JSONDecodeError, TypeError):
        challenge_data = {}

    # Active liveness validation (Layered Verification)
    active_liveness_result = photo_svc.validate_active_liveness(challenge_data, frame_bytes)
    active_liveness_passed = active_liveness_result["active_liveness_passed"]

    # Extended multi-frame liveness check
    liveness_ext = photo_svc.check_liveness_extended(frame_bytes)
    liveness_suspicious = liveness_ext["liveness_suspicious"]

    # Multi-face detection (server-side)
    multi_face = photo_svc.check_multi_face(frame_bytes)

    # Encrypt and store (Problem 2)
    storage_path = photo_svc.encrypt_and_store(loan_id, frame_bytes)

    # Update presence record
    presence = db.query(KioskPresenceRecord).filter(KioskPresenceRecord.loan_id == loan_id).first()
    if not presence:
        presence = KioskPresenceRecord(loan_id=loan_id)
        db.add(presence)

    presence.photo_hash = photo_hash
    presence.photo_encrypted_storage_path = storage_path
    presence.gps_latitude = gps_latitude
    presence.gps_longitude = gps_longitude
    presence.gps_captured_at = now
    presence.photo_captured_at = now
    presence.face_detected_client_side = face_detected_client_side
    presence.liveness_check_suspicious = liveness_suspicious
    presence.device_fingerprint = device_fingerprint
    if device_fingerprint:
        import hashlib as _hl
        presence.device_fingerprint_hash = _hl.sha256(device_fingerprint.encode()).hexdigest()

    # Active liveness fields
    presence.active_liveness_passed = active_liveness_passed
    presence.liveness_blink_detected = active_liveness_result.get("blink_verified", False)
    presence.liveness_head_turn_detected = active_liveness_result.get("head_turn_verified", False)
    presence.liveness_smile_detected = active_liveness_result.get("smile_verified", False)
    presence.liveness_challenges_json = json.dumps({
        "challenge_data": challenge_data,
        "server_validation": active_liveness_result,
        "extended_liveness": liveness_ext,
        "multi_face": multi_face,
    })
    presence.face_count_client = face_count_client
    presence.face_centered = face_centered
    presence.auto_captured = auto_captured

    # Copy assisting employee from loan → presence for record consistency
    loan = db.query(Loan).filter(Loan.loan_id == loan_id).first()
    if loan and loan.assisting_employee_name:
        presence.assisting_employee_name = loan.assisting_employee_name
        presence.assisting_employee_id = loan.assisting_employee_id

    db.commit()

    return {
        "photo_hash": photo_hash,
        "server_timestamp": now.isoformat(),
        "liveness_check_suspicious": liveness_suspicious,
        "face_detected_client_side": face_detected_client_side,
        "gps_captured": True,
        "active_liveness_passed": active_liveness_passed,
        "liveness_blink_verified": active_liveness_result.get("blink_verified", False),
        "liveness_head_turn_verified": active_liveness_result.get("head_turn_verified", False),
        "liveness_smile_verified": active_liveness_result.get("smile_verified", False),
        "multi_face_suspected": multi_face.get("multi_face_suspected", False),
        "suspicious_flags": active_liveness_result.get("suspicious_flags", []),
        "frames_received": len(frame_bytes),
    }


@router.post("/kiosk/{loan_id}/aadhaar/qr-scan", tags=["Kiosk"])
def kiosk_aadhaar_qr_scan(
    loan_id: str,
    data: dict = Body(...),
    db: Session = Depends(get_db),
    x_session_token: Optional[str] = Header(None),
):
    """Process Aadhaar QR code scan data. Stores hashed Aadhaar info and encrypts QR photo."""
    service = KioskSessionService()
    try:
        service.validate_session_token(db, loan_id, x_session_token)
        service.update_activity(db, loan_id)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))

    name = data.get("name", "").strip()
    dob = data.get("dob", "").strip()
    gender = data.get("gender", "").strip()
    address = data.get("address", "").strip()
    aadhaar_last_four = data.get("aadhaar_last_four", "").strip()
    photo_base64 = data.get("photo_base64", "")

    # Validate aadhaar_last_four
    if not aadhaar_last_four or len(aadhaar_last_four) != 4 or not aadhaar_last_four.isdigit():
        raise HTTPException(status_code=400, detail="aadhaar_last_four must be exactly 4 digits")

    if not name:
        raise HTTPException(status_code=400, detail="name is required")

    now = datetime.now(timezone.utc)

    # Update presence record
    presence = db.query(KioskPresenceRecord).filter(KioskPresenceRecord.loan_id == loan_id).first()
    if not presence:
        presence = KioskPresenceRecord(loan_id=loan_id)
        db.add(presence)

    # Hash the aadhaar_last_four using SHA-256
    presence.aadhaar_hash = hashlib.sha256(f"XXXX-XXXX-{aadhaar_last_four}".encode()).hexdigest()
    presence.aadhaar_verified_name = name
    presence.aadhaar_last_four = aadhaar_last_four
    presence.aadhaar_qr_scanned_at = now

    # Encrypt the QR photo using existing Fernet encryption
    if photo_base64:
        photo_svc = PhotoVerificationService()
        photo_bytes = photo_base64.encode('utf-8')
        photos_dir = os.path.join(os.path.dirname(__file__), "..", "..", "data", "photos")
        os.makedirs(photos_dir, exist_ok=True)
        qr_photo_path = os.path.join(photos_dir, f"{loan_id}_aadhaar_qr.enc")
        if photo_svc.fernet:
            encrypted = photo_svc.fernet.encrypt(photo_bytes)
            with open(qr_photo_path, "wb") as f:
                f.write(encrypted)
        else:
            with open(qr_photo_path, "wb") as f:
                f.write(photo_bytes)
        presence.aadhaar_qr_photo_encrypted_path = qr_photo_path

    # Update loan record
    loan = db.query(Loan).filter(Loan.loan_id == loan_id).first()
    if loan:
        loan.aadhaar_verified_name = name
        loan.status = "aadhaar_qr_scanned"

    # Update session status
    session = db.query(KioskSession).filter(KioskSession.loan_id == loan_id).first()
    if session:
        session.session_status = "aadhaar_qr_scanned"

    db.commit()

    return {
        "success": True,
        "verified_name": name,
        "aadhaar_last_four": aadhaar_last_four,
    }


@router.post("/kiosk/{loan_id}/face-match", tags=["Kiosk"])
def kiosk_face_match(
    loan_id: str,
    data: dict = Body(...),
    db: Session = Depends(get_db),
    x_session_token: Optional[str] = Header(None),
):
    """Compare Aadhaar QR photo against live captured photo for identity verification."""
    from app.services.face_match_service import compare_faces
    import base64

    service = KioskSessionService()
    try:
        service.validate_session_token(db, loan_id, x_session_token)
        service.update_activity(db, loan_id)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))

    # ── Simulated mode for demo (no real photo comparison) ──
    simulated = data.get("simulated", False)
    if simulated:
        now = datetime.now(timezone.utc)
        presence = db.query(KioskPresenceRecord).filter(KioskPresenceRecord.loan_id == loan_id).first()
        if presence:
            presence.face_match_attempts = (presence.face_match_attempts or 0) + 1
            presence.face_match_score = 0.87
            presence.face_match_passed = True

        session = db.query(KioskSession).filter(KioskSession.loan_id == loan_id).first()
        if session:
            session.session_status = "face_matched"

        db.commit()
        return {"matched": True, "score": 0.87, "error": None, "simulated": True}

    live_photo_base64 = data.get("live_photo_base64", "")
    if not live_photo_base64:
        raise HTTPException(status_code=400, detail="live_photo_base64 is required")

    # Get presence record
    presence = db.query(KioskPresenceRecord).filter(KioskPresenceRecord.loan_id == loan_id).first()
    if not presence or not presence.aadhaar_qr_photo_encrypted_path:
        raise HTTPException(status_code=400, detail="Aadhaar QR photo not found. Complete QR scan first.")

    # Decrypt the Aadhaar QR photo
    photo_svc = PhotoVerificationService()
    try:
        qr_photo_path = presence.aadhaar_qr_photo_encrypted_path
        with open(qr_photo_path, "rb") as f:
            encrypted_data = f.read()
        if photo_svc.fernet:
            aadhaar_photo_b64 = photo_svc.fernet.decrypt(encrypted_data)
        else:
            aadhaar_photo_b64 = encrypted_data
        aadhaar_photo_bytes = base64.b64decode(aadhaar_photo_b64)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to decrypt Aadhaar QR photo: {str(e)}")

    # Decode live photo
    try:
        live_photo_bytes = base64.b64decode(live_photo_base64)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid live_photo_base64 encoding")

    # Increment attempt count
    presence.face_match_attempts = (presence.face_match_attempts or 0) + 1

    # Run face comparison
    result = compare_faces(aadhaar_photo_bytes, live_photo_bytes)

    # Store results
    presence.face_match_score = result["score"]
    presence.face_match_passed = result["matched"]

    now = datetime.now(timezone.utc)

    # Log attempt in loan metadata
    loan = db.query(Loan).filter(Loan.loan_id == loan_id).first()
    if loan:
        meta = {}
        if loan.metadata_json:
            try:
                meta = json.loads(loan.metadata_json) if isinstance(loan.metadata_json, str) else (loan.metadata_json or {})
            except (json.JSONDecodeError, TypeError):
                meta = {}
        if "face_match_attempts" not in meta:
            meta["face_match_attempts"] = []
        meta["face_match_attempts"].append({
            "timestamp": now.isoformat(),
            "score": result["score"],
            "matched": result["matched"],
            "method": result.get("method", "unknown"),
            "attempt": presence.face_match_attempts,
        })
        loan.metadata_json = json.dumps(meta)

    if result["matched"]:
        # Update session and loan status
        session = db.query(KioskSession).filter(KioskSession.loan_id == loan_id).first()
        if session:
            session.session_status = "face_matched"

    db.commit()

    return {
        "matched": result["matched"],
        "score": result["score"],
        "error": result.get("error"),
    }


@router.post("/kiosk/{loan_id}/aadhaar/initiate", tags=["Kiosk"])
def kiosk_aadhaar_initiate(
    loan_id: str,
    data: dict = Body(...),
    db: Session = Depends(get_db),
    x_session_token: Optional[str] = Header(None),
    aadhaar_svc: AadhaarService = Depends(get_aadhaar_service),
):
    """Initiate Aadhaar OTP authentication. Rate limited: 3/loan/30min.
    Returns otp_display for on-screen display (demo only — production uses SMS via UIDAI)."""
    service = KioskSessionService()
    try:
        service.validate_session_token(db, loan_id, x_session_token)
        service.update_activity(db, loan_id)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))

    _check_kiosk_otp_rate_limit(f"aadhaar_{loan_id}")

    aadhaar_last_four = data.get("aadhaar_last_four")
    mobile_last_four = data.get("mobile_last_four")

    try:
        result = aadhaar_svc.initiate_auth(db, aadhaar_last_four, mobile_last_four, loan_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/kiosk/{loan_id}/aadhaar/verify", tags=["Kiosk"])
def kiosk_aadhaar_verify(
    loan_id: str,
    data: dict = Body(...),
    db: Session = Depends(get_db),
    x_session_token: Optional[str] = Header(None),
    aadhaar_svc: AadhaarService = Depends(get_aadhaar_service),
):
    """Verify Aadhaar OTP."""
    service = KioskSessionService()
    try:
        service.validate_session_token(db, loan_id, x_session_token)
        service.update_activity(db, loan_id)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))

    otp_reference_id = data.get("otp_reference_id")
    submitted_otp = data.get("otp")

    if not otp_reference_id or not submitted_otp:
        raise HTTPException(status_code=400, detail="otp_reference_id and otp are required")

    try:
        result = aadhaar_svc.verify_auth(db, otp_reference_id, submitted_otp, loan_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/kiosk/{loan_id}/document/upload", tags=["Kiosk"])
async def kiosk_document_upload(
    loan_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    x_session_token: Optional[str] = Header(None),
    doc_svc: DocumentService = Depends(get_document_service),
):
    """Upload and hash a loan document (photo of physical form)."""
    service = KioskSessionService()
    try:
        service.validate_session_token(db, loan_id, x_session_token)
        service.update_activity(db, loan_id)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))

    file_bytes = await file.read()
    if len(file_bytes) == 0:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(file_bytes) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 10MB)")

    try:
        result = doc_svc.receive_document(db, loan_id, file_bytes, file.content_type or "")
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/kiosk/{loan_id}/document/ocr", tags=["Kiosk"])
def kiosk_document_ocr(
    loan_id: str,
    db: Session = Depends(get_db),
    x_session_token: Optional[str] = Header(None),
    doc_svc: DocumentService = Depends(get_document_service),
):
    """Run OCR on the uploaded document."""
    service = KioskSessionService()
    try:
        service.validate_session_token(db, loan_id, x_session_token)
        service.update_activity(db, loan_id)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))

    try:
        result = doc_svc.run_ocr(db, loan_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/kiosk/{loan_id}/document/confirm", tags=["Kiosk"])
def kiosk_document_confirm(
    loan_id: str,
    data: dict = Body(...),
    db: Session = Depends(get_db),
    x_session_token: Optional[str] = Header(None),
    doc_svc: DocumentService = Depends(get_document_service),
):
    """Confirm OCR results with farmer-validated values."""
    service = KioskSessionService()
    try:
        service.validate_session_token(db, loan_id, x_session_token)
        service.update_activity(db, loan_id)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))

    confirmed_amount = data.get("confirmed_amount")
    confirmed_purpose = data.get("confirmed_purpose")
    attempt_number = data.get("attempt_number", 1)

    if confirmed_amount is None or not confirmed_purpose:
        raise HTTPException(status_code=400, detail="confirmed_amount and confirmed_purpose are required")

    # Extract structured confirmed fields
    confirmed_extras = {
        "account_number": data.get("confirmed_account_number"),
        "ifsc": data.get("confirmed_ifsc"),
        "phone": data.get("confirmed_phone"),
        "annual_income": data.get("confirmed_annual_income"),
        "land_ownership": data.get("confirmed_land_ownership"),
        "loan_reason": data.get("confirmed_loan_reason"),
        "confirmed_name": data.get("confirmed_name"),
    }

    try:
        result = doc_svc.confirm_ocr(
            db, loan_id, float(confirmed_amount), confirmed_purpose,
            attempt_number, confirmed_extras=confirmed_extras,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/kiosk/{loan_id}/consent/initiate", tags=["Kiosk"])
def kiosk_consent_initiate(
    loan_id: str,
    db: Session = Depends(get_db),
    x_session_token: Optional[str] = Header(None),
    consent_svc: KioskConsentService = Depends(get_kiosk_consent_service),
):
    """Generate the consent OTP (final step before signing). Rate limited: 3/loan/30min."""
    service = KioskSessionService()
    try:
        service.validate_session_token(db, loan_id, x_session_token)
        service.update_activity(db, loan_id)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))

    _check_kiosk_otp_rate_limit(f"consent_{loan_id}")

    try:
        result = consent_svc.initiate_consent_otp(db, loan_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/kiosk/{loan_id}/consent/initiate-ivr", tags=["Kiosk"])
def kiosk_consent_initiate_ivr(
    loan_id: str,
    data: dict = Body(default={}),
    db: Session = Depends(get_db),
    x_session_token: Optional[str] = Header(None),
    ivr_svc: IVRService = Depends(get_ivr_service),
):
    """Directly trigger IVR voice call for final consent — no OTP required.
    The farmer reviews the loan summary on screen and clicks to initiate the call.
    The 60-second IVR confirmation window starts immediately."""
    service = KioskSessionService()
    try:
        service.validate_session_token(db, loan_id, x_session_token)
        service.update_activity(db, loan_id)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))

    loan = db.query(Loan).filter(Loan.loan_id == loan_id).first()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")

    # Record consent initiation timestamp
    now = datetime.now(timezone.utc)
    loan.consent_given_at = now
    loan.status = "kiosk_consented"

    # Update session status
    session = db.query(KioskSession).filter(KioskSession.loan_id == loan_id).first()
    if session:
        session.session_status = "kiosk_consented"

    # Hardcoded phone number — only one Twilio-registered number available
    farmer_phone = "+916265035390"
    loan.farmer_mobile = farmer_phone

    loan.ivr_status = "pending"
    db.commit()

    result = {"consent_recorded": True, "consent_at": now.isoformat()}

    try:
        ivr_result = ivr_svc.trigger_ivr_call(
            db, loan_id,
            farmer_phone=farmer_phone,
            loan_amount=loan.amount or 0,
        )
        result["ivr_initiated"] = True
        result["ivr_simulated"] = ivr_result.get("simulated", False)
    except Exception as e:
        print(f"⚠ IVR call trigger failed: {e}")
        result["ivr_initiated"] = False
        result["ivr_error"] = str(e)

    return result


@router.post("/kiosk/{loan_id}/consent/verify", tags=["Kiosk"])
def kiosk_consent_verify(
    loan_id: str,
    data: dict = Body(...),
    db: Session = Depends(get_db),
    x_session_token: Optional[str] = Header(None),
    consent_svc: KioskConsentService = Depends(get_kiosk_consent_service),
    ivr_svc: IVRService = Depends(get_ivr_service),
):
    """Verify consent OTP, then trigger IVR voice call for final confirmation."""
    service = KioskSessionService()
    try:
        service.validate_session_token(db, loan_id, x_session_token)
        service.update_activity(db, loan_id)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))

    otp_reference_id = data.get("otp_reference_id")
    submitted_otp = data.get("otp")
    nonce = data.get("nonce")

    phone_number = data.get("phone_number")

    if not all([otp_reference_id, submitted_otp, nonce]):
        raise HTTPException(status_code=400, detail="otp_reference_id, otp, and nonce are required")

    try:
        result = consent_svc.verify_consent(db, loan_id, otp_reference_id, submitted_otp, nonce)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # OTP verified — now trigger IVR voice call (60-second window starts)
    loan = db.query(Loan).filter(Loan.loan_id == loan_id).first()
    if loan:
        # Resolve farmer phone: request body → loan record → loan_doc confirmed_phone
        farmer_phone = None
        if phone_number:
            # Format phone number for Twilio (must include country code)
            cleaned = phone_number.strip().replace(" ", "").replace("-", "")
            if not cleaned.startswith("+"):
                if len(cleaned) == 10:
                    cleaned = "+91" + cleaned  # Indian number
                elif len(cleaned) == 12 and cleaned.startswith("91"):
                    cleaned = "+" + cleaned
                else:
                    cleaned = "+" + cleaned
            farmer_phone = cleaned
            # Save to loan record for webhooks/call-status to use
            loan.farmer_mobile = farmer_phone
        elif loan.farmer_mobile:
            farmer_phone = loan.farmer_mobile
            if not farmer_phone.startswith("+"):
                farmer_phone = "+91" + farmer_phone if len(farmer_phone) == 10 else "+" + farmer_phone
        else:
            # Try loan_doc.farmer_confirmed_phone as last resort
            loan_doc = db.query(LoanDocument).filter(LoanDocument.loan_id == loan_id).first()
            if loan_doc and loan_doc.farmer_confirmed_phone:
                farmer_phone = loan_doc.farmer_confirmed_phone
                if not farmer_phone.startswith("+"):
                    farmer_phone = "+91" + farmer_phone if len(farmer_phone) == 10 else "+" + farmer_phone
                loan.farmer_mobile = farmer_phone

        if not farmer_phone:
            result["ivr_initiated"] = False
            result["ivr_error"] = "No phone number provided for IVR call"
            return result

        loan.ivr_status = "pending"
        db.commit()
        try:
            ivr_result = ivr_svc.trigger_ivr_call(
                db, loan_id,
                farmer_phone=farmer_phone,
                loan_amount=loan.amount or 0,
            )
            result["ivr_initiated"] = True
            result["ivr_simulated"] = ivr_result.get("simulated", False)
        except Exception as e:
            print(f"⚠ IVR call trigger failed: {e}")
            result["ivr_initiated"] = False
            result["ivr_error"] = str(e)

    return result


@router.post("/kiosk/{loan_id}/complete", tags=["Kiosk"])
def kiosk_complete(
    loan_id: str,
    db: Session = Depends(get_db),
    x_session_token: Optional[str] = Header(None),
    session_svc: KioskSessionService = Depends(get_kiosk_session_service),
    anchor_svc: KioskAnchorService = Depends(get_kiosk_anchor_service),
    notification: NotificationService = Depends(get_notification_service),
):
    """Complete the kiosk session: anchor on blockchain and transition to pending_clerk_review.
    Gated on IVR confirmation — ivr_status must be 'confirmed'."""
    try:
        session_svc.validate_session_token(db, loan_id, x_session_token)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))

    # Gate: IVR voice confirmation must be completed
    loan = db.query(Loan).filter(Loan.loan_id == loan_id).first()
    if loan and loan.ivr_status not in ("confirmed",):
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": "IVR_NOT_CONFIRMED",
                "message": f"IVR voice confirmation required before completion (current: {loan.ivr_status})",
                "ivr_status": loan.ivr_status,
            },
        )

    try:
        # Anchor the session
        anchor_result = anchor_svc.anchor_kiosk_session(db, loan_id)
        # Complete and invalidate session token
        session_svc.complete_session(db, loan_id)

        # Send loan_creation notification for kiosk loans (required for execution validation)
        if loan:
            try:
                farmer_mobile = loan.farmer_mobile or ""
                notification.send_loan_creation_notification(
                    db=db,
                    farmer_mobile=farmer_mobile,
                    loan_details={
                        "amount": loan.amount,
                        "purpose": loan.purpose,
                        "loan_id": loan_id,
                        "branch": "DCCB Branch",
                    },
                )
            except Exception as e:
                print(f"⚠ Kiosk loan_creation notification failed: {e}")

        return {
            "completed": True,
            "loan_id": loan_id,
            "kiosk_phase_anchor_hash": anchor_result["kiosk_phase_anchor_hash"],
            "block_number": anchor_result["block_number"],
            "status": "pending_clerk_review",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ══════════════════════════════════════════════════════════════════════
#  IVR VOICE CONFIRMATION ENDPOINTS (public webhooks + session-auth polling)
# ══════════════════════════════════════════════════════════════════════

@router.post("/ivr/webhook", tags=["IVR"])
async def ivr_webhook(
    request: Request,
    loan_id: str = Query(None),
    db: Session = Depends(get_db),
):
    """Twilio voice callback — receives DTMF digit input. Public endpoint (no JWT).
    Digit 1 = confirm, Digit 2 = reject. Checks 60-second window.
    Returns TwiML XML (Twilio requires XML, not JSON).

    CRITICAL: This endpoint MUST always return valid TwiML XML.
    Any non-XML response causes Twilio to play an error message and drop the call."""
    from fastapi.responses import Response as RawResponse

    VOICE = "Polly.Aditi"

    def twiml_say(message: str) -> RawResponse:
        """Return a TwiML <Response><Say> XML response for Twilio with Hindi voice."""
        xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<Response>"
            f'<Say voice="{VOICE}" language="hi-IN">{message}</Say>'
            "</Response>"
        )
        return RawResponse(content=xml, media_type="application/xml")

    # Bug 2: Graceful handling if loan_id query param is missing
    if not loan_id:
        print("⚠ [IVR WEBHOOK] loan_id query parameter missing")
        return twiml_say("क्षमा करें, कृपया बाद में पुनः प्रयास करें।")

    # Wrap everything in try/except — Twilio MUST receive valid TwiML
    try:
        ivr_svc = IVRService()

        loan = db.query(Loan).filter(Loan.loan_id == loan_id).first()
        if not loan:
            print(f"⚠ [IVR WEBHOOK] Loan {loan_id} not found")
            return twiml_say("ऋण नहीं मिला। धन्यवाद।")

        # Check 60-second window
        if not ivr_svc.is_within_window(loan):
            loan.ivr_status = "timed_out"
            ivr_svc.reject_loan(db, loan)
            print(f"⏱ [IVR WEBHOOK] Loan {loan_id} timed out — ignoring digit input")
            return twiml_say("समय समाप्त हो गया है। धन्यवाद।")

        # Parse form data from Twilio (Twilio sends form-encoded, not JSON)
        digits = ""
        try:
            form_data = await request.form()
            digits = form_data.get("Digits", "")
            call_sid = form_data.get("CallSid", "unknown")
            print(f"📞 [IVR WEBHOOK] Loan {loan_id} | CallSid={call_sid} | Digits={digits!r} | Raw form keys: {list(form_data.keys())}")
        except Exception as form_err:
            print(f"⚠ [IVR WEBHOOK] Form parse failed: {form_err}")

        if not digits:
            # Try JSON body as fallback (for manual testing via curl)
            try:
                body = await request.json()
                digits = str(body.get("digits", body.get("Digits", "")))
                print(f"📞 [IVR WEBHOOK] Loan {loan_id} | JSON fallback digits={digits!r}")
            except Exception:
                pass

        now = datetime.now(timezone.utc)

        if digits == "1":
            # ✅ CONFIRMED — commit status FIRST, then try auto-complete
            loan.ivr_status = "confirmed"
            loan.ivr_confirmed_at = now
            loan.consent_final_method = "ivr"
            db.commit()
            db.refresh(loan)
            print(f"✅ [IVR WEBHOOK] Loan {loan_id} CONFIRMED by farmer (digit 1)")

            # NOTE: Do NOT auto-complete the session here.
            # Completing the session invalidates the kiosk token,
            # which causes the frontend polling to get 401 and never
            # detect the confirmation. The frontend will detect
            # ivr_status='confirmed' via polling and complete the session itself.

            return twiml_say("आपकी सहमति सफलतापूर्वक दर्ज हो गई है। धन्यवाद।")

        elif digits == "2":
            # ❌ REJECTED by farmer
            loan.ivr_status = "rejected"
            loan.consent_final_method = "ivr"
            ivr_svc.reject_loan(db, loan)
            db.refresh(loan)
            print(f"❌ [IVR WEBHOOK] Loan {loan_id} REJECTED by farmer (digit 2)")
            return twiml_say("आपने ऋण आवेदन अस्वीकार कर दिया है। धन्यवाद।")

        else:
            # Invalid digit or empty — set to failed and trigger SMS fallback
            loan.ivr_status = "failed"
            db.commit()
            print(f"⚠ [IVR WEBHOOK] Loan {loan_id} — invalid digit '{digits}', triggering SMS fallback")
            farmer_phone = loan.farmer_mobile
            if farmer_phone:
                try:
                    ivr_svc.trigger_sms_fallback(
                        db, loan_id,
                        farmer_phone=farmer_phone,
                        loan_amount=loan.amount or 0,
                    )
                except Exception as sms_err:
                    print(f"⚠ [IVR WEBHOOK] SMS fallback trigger failed: {sms_err}")
            else:
                print(f"⚠ [IVR WEBHOOK] No phone number on loan {loan_id} — cannot send SMS")
            return twiml_say("अमान्य इनपुट। SMS द्वारा पुष्टि भेजी जा रही है।")

    except Exception as e:
        # CRITICAL: Always return valid TwiML even on server error
        print(f"❌ [IVR WEBHOOK] UNHANDLED ERROR for loan {loan_id}: {e}")
        import traceback
        traceback.print_exc()
        return twiml_say("तकनीकी त्रुटि। कृपया बाद में प्रयास करें। धन्यवाद।")


@router.post("/ivr/sms-webhook", tags=["IVR"])
async def ivr_sms_webhook(
    request: Request,
    loan_id: str = Query(None),
    db: Session = Depends(get_db),
):
    """Twilio SMS reply webhook — farmer replies YES/NO. Public endpoint (no JWT).
    Checks 60-second window. Returns TwiML XML for Twilio."""
    from fastapi.responses import Response as RawResponse

    def twiml_sms(message: str) -> RawResponse:
        xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Response>'
            f'<Message>{message}</Message>'
            '</Response>'
        )
        return RawResponse(content=xml, media_type="application/xml")

    try:
        ivr_svc = IVRService()

        # Parse form data from Twilio
        form_data = await request.form()
        body_text = form_data.get("Body", "")
        from_number = form_data.get("From", "")

        if not body_text:
            try:
                json_body = await request.json()
                body_text = str(json_body.get("Body", json_body.get("body", "")))
                loan_id = loan_id or str(json_body.get("loan_id", ""))
            except Exception:
                pass

        if not loan_id:
            return twiml_sms("Error: loan_id required")

        loan = db.query(Loan).filter(Loan.loan_id == loan_id).first()
        if not loan:
            return twiml_sms("Error: Loan not found")

        # Check 60-second window
        if not ivr_svc.is_within_window(loan):
            loan.ivr_status = "timed_out"
            ivr_svc.reject_loan(db, loan)
            print(f"⏱ [SMS WEBHOOK] Loan {loan_id} timed out — ignoring SMS reply")
            return twiml_sms("समय समाप्त। Time expired.")

        reply = body_text.strip().upper()
        now = datetime.now(timezone.utc)

        if reply == "YES":
            loan.ivr_status = "confirmed"
            loan.ivr_confirmed_at = now
            loan.consent_final_method = "sms"
            db.commit()
            db.refresh(loan)
            print(f"✅ [SMS WEBHOOK] Loan {loan_id} CONFIRMED by SMS reply")

            # Auto-complete (best-effort)
            try:
                anchor_svc = KioskAnchorService()
                session_svc = KioskSessionService()
                anchor_result = anchor_svc.anchor_kiosk_session(db, loan_id)
                session_svc.complete_session(db, loan_id)
                print(f"✅ [SMS] Auto-completed kiosk session for loan {loan_id}")
            except Exception as e:
                print(f"⚠ [SMS] Auto-complete failed for {loan_id} (frontend will retry): {e}")

            return twiml_sms("✅ ऋण पुष्टि हो गई। Loan confirmed.")

        elif reply == "NO":
            loan.ivr_status = "rejected"
            loan.consent_final_method = "sms"
            ivr_svc.reject_loan(db, loan)
            db.refresh(loan)
            print(f"❌ [SMS WEBHOOK] Loan {loan_id} REJECTED by SMS reply")
            return twiml_sms("❌ ऋण अस्वीकृत। Loan rejected.")

        else:
            print(f"⚠ [SMS WEBHOOK] Loan {loan_id} — unrecognized reply: '{reply}'")
            return twiml_sms("Reply YES or NO. YES या NO लिखें।")

    except Exception as e:
        print(f"❌ [SMS WEBHOOK] Error: {e}")
        import traceback
        traceback.print_exc()
        return twiml_sms("Error processing request.")


@router.post("/ivr/call-status", tags=["IVR"])
async def ivr_call_status(
    request: Request,
    loan_id: str = Query(None),
    db: Session = Depends(get_db),
):
    """Twilio call status callback — handles failed/busy/no-answer calls.
    Public endpoint. Returns TwiML XML. Triggers SMS fallback on call failure."""
    from fastapi.responses import Response as RawResponse

    def twiml_ok() -> RawResponse:
        xml = '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'
        return RawResponse(content=xml, media_type="application/xml")

    try:
        form_data = await request.form()
        call_status = form_data.get("CallStatus", "")

        print(f"📞 [CALL STATUS] Loan {loan_id} | CallStatus={call_status}")

        if not loan_id:
            return twiml_ok()

        loan = db.query(Loan).filter(Loan.loan_id == loan_id).first()
        if not loan:
            return twiml_ok()

        if call_status == "completed":
            print(f"📞 [CALL STATUS] Loan {loan_id} — call completed normally (ivr_status={loan.ivr_status})")
        elif call_status in ("busy", "no-answer", "failed", "canceled") and loan.ivr_status == "pending":
            print(f"📞 [CALL STATUS] Loan {loan_id} — call {call_status}, triggering SMS fallback")
            ivr_svc = IVRService()
            farmer_phone = loan.farmer_mobile
            if farmer_phone:
                try:
                    ivr_svc.trigger_sms_fallback(
                        db, loan_id,
                        farmer_phone=farmer_phone,
                        loan_amount=loan.amount or 0,
                    )
                except Exception as e:
                    print(f"⚠ [CALL STATUS] SMS fallback failed: {e}")
            else:
                print(f"⚠ [CALL STATUS] No phone number on loan {loan_id} — cannot send SMS fallback")

        return twiml_ok()

    except Exception as e:
        print(f"❌ [CALL STATUS] Error: {e}")
        return RawResponse(
            content='<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
            media_type="application/xml",
        )


@router.get("/kiosk/{loan_id}/ivr-status", tags=["Kiosk"])
def kiosk_ivr_status(
    loan_id: str,
    db: Session = Depends(get_db),
    x_session_token: Optional[str] = Header(None),
):
    """Poll IVR confirmation status. Session token auth.
    Also enforces 60-second timeout on every poll."""
    service = KioskSessionService()
    try:
        service.validate_session_token(db, loan_id, x_session_token)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))

    # Bug 7: Expire all cached objects to ensure fresh DB read
    db.expire_all()
    loan = db.query(Loan).filter(Loan.loan_id == loan_id).first()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")

    # Enforce timeout check on every poll
    ivr_svc = IVRService()
    ivr_svc.check_ivr_timeout(db, loan)
    db.refresh(loan)

    # Calculate remaining time
    remaining = 0
    if loan.ivr_window_started_at:
        window_start = loan.ivr_window_started_at
        if window_start.tzinfo is None:
            window_start = window_start.replace(tzinfo=timezone.utc)
        elapsed = (datetime.now(timezone.utc) - window_start).total_seconds()
        remaining = max(0, 300 - elapsed)

    return {
        "ivr_status": loan.ivr_status,
        "ivr_attempts": loan.ivr_attempts or 0,
        "consent_final_method": loan.consent_final_method,
        "ivr_confirmed_at": loan.ivr_confirmed_at.isoformat() if loan.ivr_confirmed_at else None,
        "ivr_window_started_at": loan.ivr_window_started_at.isoformat() if loan.ivr_window_started_at else None,
        "remaining_seconds": round(remaining, 1),
        "loan_status": loan.status,
    }


@router.post("/kiosk/{loan_id}/assistance/request", tags=["Kiosk"])
def kiosk_assistance_request(
    loan_id: str,
    db: Session = Depends(get_db),
    x_session_token: Optional[str] = Header(None),
    doc_svc: DocumentService = Depends(get_document_service),
):
    """Request employee assistance for the kiosk session."""
    service = KioskSessionService()
    try:
        service.validate_session_token(db, loan_id, x_session_token)
        service.update_activity(db, loan_id)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))

    try:
        result = doc_svc.activate_employee_assistance(db, loan_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/kiosk/status/{loan_id}", tags=["Kiosk"])
def kiosk_public_status(
    loan_id: str,
    db: Session = Depends(get_db),
):
    """Public endpoint — limited status for receipt QR codes. No auth required."""
    loan = db.query(Loan).filter(Loan.loan_id == loan_id).first()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")

    # Map internal status to human-readable display
    status_display_map = {
        "kiosk_started": "Received", "aadhaar_verified": "Received",
        "document_uploaded": "Received", "ocr_confirmed": "Received",
        "kiosk_consented": "Received", "kiosk_anchored": "Received",
        "pending_clerk_review": "Under Review", "pending_approvals": "Under Review",
        "cbs_validated": "Under Review", "ready_for_execution": "Under Review",
        "executed": "Approved", "anchored": "Approved",
        "rejected": "Rejected", "clerk_rejected": "Rejected", "kiosk_expired": "Expired",
        "kiosk_rejected": "Rejected",
    }
    status_display = status_display_map.get(loan.status, "Under Review")

    return {
        "loan_id": loan.loan_id,
        "status_display": status_display,
        "submitted_at": loan.created_at.isoformat() if loan.created_at else None,
    }


@router.get("/kiosk/{loan_id}/status", tags=["Kiosk"])
def kiosk_status(
    loan_id: str,
    db: Session = Depends(get_db),
    x_session_token: Optional[str] = Header(None),
):
    """Get current kiosk session status (session token optional for polling)."""
    session = db.query(KioskSession).filter(KioskSession.loan_id == loan_id).first()
    loan = db.query(Loan).filter(Loan.loan_id == loan_id).first()
    presence = db.query(KioskPresenceRecord).filter(KioskPresenceRecord.loan_id == loan_id).first()
    loan_doc = db.query(LoanDocument).filter(LoanDocument.loan_id == loan_id).first()

    if not session:
        raise HTTPException(status_code=404, detail="Kiosk session not found")

    return {
        "session_status": session.session_status,
        "loan_status": loan.status if loan else None,
        "aadhaar_verified": presence.aadhaar_otp_verified if presence else False,
        "aadhaar_verified_name": presence.aadhaar_verified_name if presence else None,
        "document_uploaded": loan_doc is not None and loan_doc.document_hash is not None,
        "ocr_completed": loan_doc.ocr_extracted_amount is not None if loan_doc else False,
        "ocr_confirmed": loan_doc.ocr_confirmed_at is not None if loan_doc else False,
        "amount": loan.amount if loan else None,
        "purpose": loan.purpose if loan else None,
        "farmer_name": loan.farmer_name or loan.aadhaar_verified_name if loan else None,
    }



@router.get("/kiosk/{loan_id}/evidence", tags=["Clerk", "Audit"])
def get_kiosk_evidence(
    loan_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Get complete kiosk session evidence package for a loan."""
    session = db.query(KioskSession).filter(KioskSession.loan_id == loan_id).first()
    loan = db.query(Loan).filter(Loan.loan_id == loan_id).first()
    presence = db.query(KioskPresenceRecord).filter(KioskPresenceRecord.loan_id == loan_id).first()
    loan_doc = db.query(LoanDocument).filter(LoanDocument.loan_id == loan_id).first()
    consent = db.query(FarmerConsent).filter(FarmerConsent.loan_id == loan_id).first()
    otp_records = db.query(ConsentOTPRecord).filter(ConsentOTPRecord.loan_id == loan_id).all()

    if not session:
        raise HTTPException(status_code=404, detail="No kiosk session found for this loan")

    return {
        "session": {
            "session_id": session.session_id,
            "status": session.session_status,
            "started_at": session.session_started_at.isoformat() if session.session_started_at else None,
            "completed_at": session.session_completed_at.isoformat() if session.session_completed_at else None,
            "ip_address": session.ip_address,
        },
        "presence": {
            "gps_latitude": presence.gps_latitude if presence else None,
            "gps_longitude": presence.gps_longitude if presence else None,
            "photo_hash": presence.photo_hash if presence else None,
            "aadhaar_last_four": presence.aadhaar_last_four if presence else None,
            "aadhaar_verified_name": presence.aadhaar_verified_name if presence else None,
            "aadhaar_otp_verified": presence.aadhaar_otp_verified if presence else False,
            "terms_accepted_at": presence.terms_accepted_at.isoformat() if presence and presence.terms_accepted_at else None,
            "aadhaar_verified_at": presence.aadhaar_verified_at.isoformat() if presence and presence.aadhaar_verified_at else None,
            "aadhaar_qr_scanned_at": presence.aadhaar_qr_scanned_at.isoformat() if presence and hasattr(presence, 'aadhaar_qr_scanned_at') and presence.aadhaar_qr_scanned_at else None,
            "photo_captured_at": presence.photo_captured_at.isoformat() if presence and presence.photo_captured_at else None,
            "face_match_passed": presence.face_match_passed if presence and hasattr(presence, 'face_match_passed') else None,
        } if presence else None,
        "document": {
            "document_hash": loan_doc.document_hash if loan_doc else None,
            "ocr_extracted_amount": loan_doc.ocr_extracted_amount if loan_doc else None,
            "ocr_extracted_purpose": loan_doc.ocr_extracted_purpose if loan_doc else None,
            "ocr_extracted_farmer_name": loan_doc.ocr_extracted_farmer_name if loan_doc else None,
            "ocr_confidence_score": loan_doc.ocr_confidence_score if loan_doc else None,
            "farmer_confirmed_amount": loan_doc.farmer_confirmed_amount if loan_doc else None,
            "farmer_confirmed_purpose": loan_doc.farmer_confirmed_purpose if loan_doc else None,
            "ocr_confirmation_attempts": loan_doc.ocr_confirmation_attempts if loan_doc else None,
            "employee_assistance_used": loan_doc.employee_assistance_used if loan_doc else False,
            "ocr_confirmed_at": loan_doc.ocr_confirmed_at.isoformat() if loan_doc and loan_doc.ocr_confirmed_at else None,
            "document_uploaded_at": loan_doc.document_uploaded_at.isoformat() if loan_doc and loan_doc.document_uploaded_at else None,
        } if loan_doc else None,
        "consent": {
            "consent_method": consent.consent_method if consent else None,
            "consented_at": consent.consented_at.isoformat() if consent and consent.consented_at else None,
        } if consent else None,
        "ivr_consent": {
            "ivr_status": loan.ivr_status if loan else None,
            "ivr_confirmed_at": loan.ivr_confirmed_at.isoformat() if loan and loan.ivr_confirmed_at else None,
            "consent_final_method": loan.consent_final_method if loan else None,
            "consent_given_at": loan.consent_given_at.isoformat() if loan and hasattr(loan, 'consent_given_at') and loan.consent_given_at else None,
            "ivr_window_started_at": loan.ivr_window_started_at.isoformat() if loan and loan.ivr_window_started_at else None,
            "ivr_attempts": loan.ivr_attempts if loan else 0,
        } if loan else None,
        "farmer_name": loan.farmer_name if loan else None,
        "farmer_confirmed_name": loan.farmer_name if loan else None,
        "otp_records": [
            {
                "otp_type": r.otp_type,
                "used": r.used,
                "verified_at": r.verified_at.isoformat() if r.verified_at else None,
                "attempt_count": r.attempt_count,
                "mobile_last_four": r.mobile_last_four if hasattr(r, 'mobile_last_four') else None,
            }
            for r in otp_records
        ],
        "kiosk_phase_anchor_hash": loan.kiosk_phase_anchor_hash if loan else None,
        "kiosk_completed_at": loan.kiosk_completed_at.isoformat() if loan and loan.kiosk_completed_at else None,
        "assistance_session": loan.assistance_session if loan else False,
        "assisting_employee_name": loan.assisting_employee_name if loan else None,
        "assisting_employee_id": loan.assisting_employee_id if loan else None,
    }


@router.post("/kiosk/{loan_id}/assistance/confirm", tags=["Clerk"])
def kiosk_assistance_confirm(
    loan_id: str,
    data: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_roles("clerk", "branch_manager")),
):
    """Clerk confirms physical presence for an assisted kiosk session."""
    employee_id = current_user.get("user_id")
    assistance_code = data.get("assistance_code")

    if not assistance_code:
        raise HTTPException(status_code=400, detail="assistance_code is required")

    doc_svc = DocumentService()
    try:
        result = doc_svc.confirm_assistance(db, loan_id, employee_id, assistance_code)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ══════════════════════════════════════════════════════════════════════
#  AUDIT: Kiosk Photo Retrieval
# ══════════════════════════════════════════════════════════════════════

@router.get("/audit/kiosk-photo/{loan_id}", tags=["Audit", "Clerk"])
def get_kiosk_photo(
    loan_id: str,
    request: Request,
    format: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_roles("auditor", "ceo", "clerk")),
):
    """Retrieve encrypted kiosk photo for audit/clerk review purposes.
    Decrypts the stored photo. With ?format=json returns all frames as base64.
    Without format param, returns first frame as JPEG (backward-compatible).
    Every access is logged."""
    import logging
    import base64
    audit_logger = logging.getLogger("cge.audit")
    audit_logger.info(
        f"Kiosk photo accessed: loan_id={loan_id}, user={current_user.get('user_id')}, "
        f"role={current_user.get('role')}, ip={request.client.host if request.client else 'unknown'}"
    )

    photo_svc = PhotoVerificationService()
    try:
        frames = photo_svc.decrypt_photo(loan_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="No photo found for this loan")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to decrypt photo: {str(e)}")

    # JSON format: return all frames as base64
    if format == "json":
        return {
            "loan_id": loan_id,
            "total_frames": len(frames),
            "frames": [
                {
                    "frame_number": i + 1,
                    "data": base64.b64encode(frame).decode("utf-8"),
                    "size_bytes": len(frame),
                }
                for i, frame in enumerate(frames)
            ],
        }

    # Default: return first frame as JPEG (backward-compatible)
    return StreamingResponse(
        io.BytesIO(frames[0]),
        media_type="image/jpeg",
        headers={"Content-Disposition": f"inline; filename=kiosk_photo_{loan_id}.jpg"}
    )


# ══════════════════════════════════════════════════════════════════════
#  AUDIT: Kiosk Document Retrieval
# ══════════════════════════════════════════════════════════════════════

@router.get("/audit/kiosk-document/{loan_id}", tags=["Audit", "Clerk"])
def get_kiosk_document(
    loan_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_roles("auditor", "ceo", "clerk")),
):
    """Retrieve encrypted kiosk document for clerk review / audit purposes.
    Decrypts the stored document and returns as image. Every access is logged."""
    import logging
    audit_logger = logging.getLogger("cge.audit")
    audit_logger.info(
        f"Kiosk document accessed: loan_id={loan_id}, user={current_user.get('user_id')}, "
        f"role={current_user.get('role')}, ip={request.client.host if request.client else 'unknown'}"
    )

    loan_doc = db.query(LoanDocument).filter(LoanDocument.loan_id == loan_id).first()
    if not loan_doc or not loan_doc.encrypted_document_path:
        raise HTTPException(status_code=404, detail="No document found for this loan")

    import os
    if not os.path.exists(loan_doc.encrypted_document_path):
        raise HTTPException(status_code=404, detail="Document file not found on disk")

    doc_svc = DocumentService()
    try:
        with open(loan_doc.encrypted_document_path, "rb") as f:
            encrypted_data = f.read()
        decrypted = doc_svc.fernet.decrypt(encrypted_data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to decrypt document: {str(e)}")

    # Detect content type
    content_type = "image/jpeg"
    if decrypted[:4] == b'\x89PNG':
        content_type = "image/png"
    elif decrypted[:4] == b'%PDF':
        content_type = "application/pdf"

    return StreamingResponse(
        io.BytesIO(decrypted),
        media_type=content_type,
        headers={"Content-Disposition": f"inline; filename=document_{loan_id}"}
    )


# ── TEST ENDPOINT: Skip to IVR consent step ──
@router.get("/test/ivr-ready")
def test_create_ivr_ready_loan(db: Session = Depends(get_db)):
    """
    Creates a loan pre-filled to the IVR consent step for testing.
    Returns loan_id and session_token so you can test IVR without going through 9 steps.
    """
    import secrets
    from datetime import datetime, timezone, timedelta

    loan_id = f"LN_TEST_{int(datetime.now(timezone.utc).timestamp())}"
    token = secrets.token_hex(32)
    session_id = secrets.token_hex(16)

    # Create loan with minimal required fields
    loan = Loan(
        loan_id=loan_id,
        farmer_name="Test Farmer",
        farmer_mobile="+916265035390",
        amount=50000.0,
        purpose="Agriculture",
        status="pending",
        ivr_status="pending",
    )
    db.add(loan)

    # Create kiosk session with required fields
    session = KioskSession(
        session_id=session_id,
        loan_id=loan_id,
        session_token=token,
        session_token_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        session_status="active",
    )
    db.add(session)
    db.commit()

    print(f"🧪 [TEST] Created IVR-ready loan {loan_id} with session token")

    return {
        "loan_id": loan_id,
        "session_token": token,
        "message": "Loan created at consent step. Use the kiosk app or curl to test IVR.",
        "test_ivr_curl": f"curl -X POST {os.getenv('VOICE_WEBHOOK_BASE_URL', 'https://csicfinal-production.up.railway.app')}/api/kiosk/{loan_id}/consent/initiate-ivr -H 'X-Session-Token: {token}' -H 'Content-Type: application/json' -d '{{}}'",
    }
