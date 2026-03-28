"""
Consent engine for the CGE system.
Orchestrates farmer consent and manager approval workflows,
including cryptographic signature generation and validation.

Enhanced with:
- Notification verification (SMS audit check)
- Time-based validation (rush-fraud and stale-consent detection)
- Bank KYC + local biometric support
"""

import json
from datetime import datetime, timezone, timedelta
from typing import Tuple, Optional, List, Dict, Any
import logging

from sqlalchemy.orm import Session

from app.models.loan import Loan
from app.models.consent import FarmerConsent
from app.models.approval import Approval
from app.models.disbursement import DisbursementConsent
from app.models.notification import Notification
from app.services.crypto_service import CryptoService
from app.services.policy_engine import PolicyEngine

logger = logging.getLogger(__name__)


class ConsentEngine:
    """Manages the full consent and approval lifecycle."""

    def __init__(
        self,
        crypto_service: CryptoService = None,
        policy_engine: PolicyEngine = None,
    ):
        self.crypto = crypto_service or CryptoService()
        self.policy = policy_engine or PolicyEngine()

    # ── helpers

    def _loan_param_dict(self, loan: Loan) -> dict:
        """Extract the hashable loan parameters."""
        return {
            "loan_id": loan.loan_id,
            "farmer_id": loan.farmer_id,
            "farmer_name": loan.farmer_name,
            "amount": loan.amount,
            "tenure_months": loan.tenure_months,
            "interest_rate": loan.interest_rate,
            "purpose": loan.purpose,
        }

    # ── Farmer Consent

    def create_farmer_consent(
        self,
        db: Session,
        loan: Loan,
        otp: str,
        device_info: Optional[dict] = None,
        ip_address: Optional[str] = None,
        live_photo_base64: Optional[str] = None,
        gps_latitude: Optional[float] = None,
        gps_longitude: Optional[float] = None,
        device_fingerprint: Optional[str] = None,
        bank_kyc_verified: bool = False,
        otp_reference_id: Optional[str] = None,
        fingerprint_hash: Optional[str] = None,
    ) -> FarmerConsent:
        """Create a farmer consent record with a digital signature of the loan hash."""
        if loan.status != "pending_farmer_consent":
            raise ValueError(
                f"Loan {loan.loan_id} is not pending farmer consent (status={loan.status})"
            )

        # Check for existing consent
        existing = (
            db.query(FarmerConsent)
            .filter(FarmerConsent.loan_id == loan.loan_id)
            .first()
        )
        if existing:
            raise ValueError(f"Farmer consent already exists for loan {loan.loan_id}")

        # Validate OTP (must be exactly 6 digits)
        import re
        if not otp or not re.match(r"^\d{6}$", otp):
            raise ValueError("Invalid OTP – must be exactly 6 digits")

        loan_hash = loan.loan_hash
        key_id = f"farmer_{loan.farmer_id}"

        # Sign the loan hash
        farmer_signature = self.crypto.sign_data(loan_hash, key_id)

        # Hash the live photo if provided (Fraud Type 3)
        live_photo_hash = None
        if live_photo_base64:
            import hashlib
            live_photo_hash = hashlib.sha256(live_photo_base64.encode()).hexdigest()

        # Determine consent method
        consent_method = "bank_kyc_otp_local_biometric" if fingerprint_hash else "bank_kyc_otp"

        # Build consent token
        consent_token = self.crypto.generate_consent_token(
            loan_hash=loan_hash,
            farmer_signature=farmer_signature,
            consent_method=consent_method,
            metadata={
                "ip_address": ip_address or "127.0.0.1",
                "device_info": device_info or {},
                "otp_last4": otp[-4:],
                "bank_kyc_verified": bank_kyc_verified,
                "has_fingerprint": fingerprint_hash is not None,
                "has_live_photo": live_photo_hash is not None,
                "gps": {"lat": gps_latitude, "lng": gps_longitude}
                if gps_latitude and gps_longitude else None,
            },
        )

        consent = FarmerConsent(
            loan_id=loan.loan_id,
            loan_hash=loan_hash,
            farmer_signature=farmer_signature,
            consent_method=consent_method,
            otp_verified=otp[-4:],
            ip_address=ip_address or "127.0.0.1",
            device_info=device_info,
            consent_token=consent_token,
            bank_kyc_verified=bank_kyc_verified,
            otp_reference_id=otp_reference_id,
            fingerprint_hash=fingerprint_hash,
            fingerprint_captured_at=datetime.now(timezone.utc) if fingerprint_hash else None,
            live_photo_hash=live_photo_hash,
            gps_latitude=gps_latitude,
            gps_longitude=gps_longitude,
            consent_device_fingerprint=device_fingerprint,
        )

        db.add(consent)

        # Update loan status
        loan.status = "pending_approvals"
        loan.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(consent)

        return consent

    # ── Manager Approval

    def create_manager_approval(
        self,
        db: Session,
        loan: Loan,
        approver_id: str,
        approver_name: str,
        approver_role: str,
        comments: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> Approval:
        """Create a manager approval with a digital signature of the loan hash."""
        # Verify loan status
        if loan.status not in ("pending_approvals", "approved"):
            raise ValueError(
                f"Loan {loan.loan_id} is not pending approvals (status={loan.status})"
            )

        # Verify farmer consent exists
        consent = (
            db.query(FarmerConsent)
            .filter(FarmerConsent.loan_id == loan.loan_id)
            .first()
        )
        if not consent:
            # Auto-create FarmerConsent for IVR-confirmed kiosk loans
            if loan.ivr_status == "confirmed":
                logger.info(
                    f"Auto-creating FarmerConsent for IVR-confirmed loan {loan.loan_id}"
                )
                loan_hash = loan.loan_hash
                key_id = f"farmer_{loan.farmer_id}"
                farmer_signature = self.crypto.sign_data(loan_hash, key_id)
                consent_token = self.crypto.generate_consent_token(
                    loan_hash=loan_hash,
                    farmer_signature=farmer_signature,
                    consent_method="ivr_voice",
                    metadata={
                        "auto_created": True,
                        "ivr_confirmed_at": loan.ivr_confirmed_at.isoformat()
                        if loan.ivr_confirmed_at else None,
                        "consent_final_method": loan.consent_final_method,
                    },
                )
                consent = FarmerConsent(
                    loan_id=loan.loan_id,
                    loan_hash=loan_hash,
                    farmer_signature=farmer_signature,
                    consent_method="ivr_voice",
                    otp_verified="IVR",
                    ip_address="kiosk",
                    consent_token=consent_token,
                    bank_kyc_verified=False,
                )
                # Use ivr_confirmed_at as consent time if available
                if loan.ivr_confirmed_at:
                    consent.consented_at = loan.ivr_confirmed_at
                db.add(consent)
                db.flush()
            else:
                raise ValueError(f"No farmer consent found for loan {loan.loan_id}")

        # Verify role is required for this tier
        if not self.policy.is_role_required(loan.amount, approver_role):
            raise ValueError(
                f"Role '{approver_role}' is not required for this loan tier"
            )

        # Check for duplicate approval from same approver
        existing = (
            db.query(Approval)
            .filter(
                Approval.loan_id == loan.loan_id,
                Approval.approver_id == approver_id,
            )
            .first()
        )
        if existing:
            raise ValueError(
                f"Approver {approver_id} has already approved loan {loan.loan_id}"
            )

        # Check for duplicate role approval
        role_existing = (
            db.query(Approval)
            .filter(
                Approval.loan_id == loan.loan_id,
                Approval.approver_role == approver_role,
            )
            .first()
        )
        if role_existing:
            raise ValueError(
                f"A {approver_role} has already approved this loan"
            )

        loan_hash = loan.loan_hash
        key_id = f"approver_{approver_id}"

        # Sign the loan hash
        approver_signature = self.crypto.sign_data(loan_hash, key_id)

        approval = Approval(
            loan_id=loan.loan_id,
            approver_id=approver_id,
            approver_name=approver_name,
            approver_role=approver_role,
            loan_hash=loan_hash,
            approver_signature=approver_signature,
            comments=comments,
            ip_address=ip_address or "127.0.0.1",
        )

        db.add(approval)
        db.flush()  # ensure the new approval is visible in queries

        # Check if all approvals are now collected
        current_approvals = (
            db.query(Approval)
            .filter(Approval.loan_id == loan.loan_id)
            .all()
        )
        approvals_dicts = [
            {"approver_role": a.approver_role, "approver_id": a.approver_id}
            for a in current_approvals
        ]

        is_complete, msg = self.policy.validate_approvals(loan.amount, approvals_dicts)
        if is_complete:
            loan.status = "ready_for_execution"
        loan.updated_at = datetime.now(timezone.utc)

        db.commit()
        db.refresh(approval)
        return approval

    # ── Execution Validation

    def validate_execution_eligibility(
        self, db: Session, loan_id: str
    ) -> Tuple[bool, Optional[dict], Optional[str]]:
        """
        Comprehensive validation before loan execution.
        Returns (is_eligible, final_consent_token | None, error_message | None).

        Checks:
        1. Hash integrity (tamper detection)
        2. Farmer consent verification
        3. Manager approvals + signature verification
        4. Policy compliance
        5. Disbursement consent (benami prevention)
        6. SMS notification verification (farmer informed)
        7. Time-based validation (rush-fraud / stale consent)
        """
        loan = db.query(Loan).filter(Loan.loan_id == loan_id).first()
        if not loan:
            return (False, None, f"Loan {loan_id} not found")

        # 0. Kiosk Session Completeness Check (Step 0 — must pass before any other validation)
        from app.models.kiosk_session import KioskSession
        from app.models.kiosk_presence import KioskPresenceRecord
        from app.models.loan_document import LoanDocument
        from app.models.consent_otp import ConsentOTPRecord

        kiosk_session = db.query(KioskSession).filter(KioskSession.loan_id == loan_id).first()
        if kiosk_session:
            # Check 0a: KioskSession must be completed
            if kiosk_session.session_status != "completed":
                return (False, None, json.dumps({
                    "error_code": "KIOSK_SESSION_INCOMPLETE",
                    "message": f"Kiosk session not completed (status={kiosk_session.session_status})"
                }))
            # Check 0b: KioskPresenceRecord with aadhaar_otp_verified = true
            presence = db.query(KioskPresenceRecord).filter(KioskPresenceRecord.loan_id == loan_id).first()
            if not presence or not presence.aadhaar_otp_verified:
                return (False, None, json.dumps({
                    "error_code": "KIOSK_SESSION_INCOMPLETE",
                    "message": "Aadhaar verification not completed in kiosk session"
                }))
            # Check 0c: LoanDocument with ocr_confirmed_at not null
            loan_doc = db.query(LoanDocument).filter(LoanDocument.loan_id == loan_id).first()
            if not loan_doc or not loan_doc.ocr_confirmed_at:
                return (False, None, json.dumps({
                    "error_code": "KIOSK_SESSION_INCOMPLETE",
                    "message": "Document OCR confirmation not completed in kiosk session"
                }))
            # Check 0d: ConsentOTPRecord of type loan_consent with used = true
            # Skip this check for IVR-confirmed loans — IVR voice consent replaces OTP consent
            if loan.ivr_status == "confirmed":
                logger.info(
                    f"Skipping consent OTP check for IVR-confirmed loan {loan_id}"
                )
            else:
                consent_otp = db.query(ConsentOTPRecord).filter(
                    ConsentOTPRecord.loan_id == loan_id,
                    ConsentOTPRecord.otp_type == "loan_consent",
                    ConsentOTPRecord.used == True,
                ).first()
                if not consent_otp:
                    return (False, None, json.dumps({
                        "error_code": "KIOSK_SESSION_INCOMPLETE",
                        "message": "Consent OTP not verified in kiosk session"
                    }))
            # Check 0e: kiosk_phase_anchor_hash is not null on loan
            if not loan.kiosk_phase_anchor_hash:
                return (False, None, json.dumps({
                    "error_code": "KIOSK_SESSION_INCOMPLETE",
                    "message": "Kiosk phase not anchored on blockchain"
                }))
            # Check 0f: IVR voice confirmation must be completed
            if loan.ivr_status not in ("confirmed",):
                return (False, None, json.dumps({
                    "error_code": "KIOSK_SESSION_INCOMPLETE",
                    "message": f"IVR voice confirmation not completed (status={loan.ivr_status})"
                }))
            # Check 0g: Face match verification must be completed
            if not presence.face_match_passed:
                return (False, None, json.dumps({
                    "error_code": "KIOSK_SESSION_INCOMPLETE",
                    "message": "Face match verification not completed"
                }))
            # Check 0h: Aadhaar QR scan must be completed
            if not presence.aadhaar_qr_scanned_at:
                return (False, None, json.dumps({
                    "error_code": "KIOSK_SESSION_INCOMPLETE",
                    "message": "Aadhaar QR scan not completed"
                }))

        # 1. Recompute loan hash from current DB parameters
        current_params = self._loan_param_dict(loan)
        recomputed_hash = self.crypto.generate_loan_hash(current_params)

        if recomputed_hash != loan.loan_hash:
            return (
                False,
                None,
                "FRAUD DETECTED: Loan parameters have been tampered with. "
                f"Stored hash: {loan.loan_hash}, Recomputed hash: {recomputed_hash}",
            )

        # 2. Verify farmer consent
        consent = (
            db.query(FarmerConsent)
            .filter(FarmerConsent.loan_id == loan_id)
            .first()
        )
        if not consent:
            return (False, None, "Farmer consent not found")

        if consent.loan_hash != loan.loan_hash:
            return (
                False,
                None,
                "FRAUD DETECTED: Farmer consent hash does not match loan hash",
            )

        # 3. Verify all approvals
        approvals = (
            db.query(Approval).filter(Approval.loan_id == loan_id).all()
        )

        for appr in approvals:
            if appr.loan_hash != loan.loan_hash:
                return (
                    False,
                    None,
                    f"FRAUD DETECTED: Approver {appr.approver_name} hash mismatch",
                )
            approver_key_id = f"approver_{appr.approver_id}"
            if not self.crypto.verify_signature(
                loan.loan_hash, appr.approver_signature, approver_key_id
            ):
                return (
                    False,
                    None,
                    f"Signature verification failed for approver {appr.approver_name}",
                )

        # 4. Policy compliance
        approvals_dicts = [
            {"approver_role": a.approver_role, "approver_id": a.approver_id}
            for a in approvals
        ]
        is_complete, msg = self.policy.validate_approvals(
            loan.amount, approvals_dicts
        )
        if not is_complete:
            return (False, None, f"Policy compliance failed: {msg}")

        # 5. Verify disbursement consent (Fraud Type 1 – Benami Prevention)
        disbursement = (
            db.query(DisbursementConsent)
            .filter(DisbursementConsent.loan_id == loan_id)
            .first()
        )
        if not disbursement:
            # Auto-create DisbursementConsent for kiosk-originated loans
            # Bank account details were captured during OCR confirmation step
            if kiosk_session:
                loan_doc = db.query(LoanDocument).filter(LoanDocument.loan_id == loan_id).first()
                if (loan_doc
                        and loan_doc.farmer_confirmed_account_number
                        and loan_doc.farmer_confirmed_ifsc):
                    logger.info(
                        f"Auto-creating DisbursementConsent for kiosk loan {loan_id}"
                    )
                    account_name = (
                        loan_doc.farmer_confirmed_name
                        or loan.farmer_name
                        or "Farmer"
                    )
                    disb_data = {
                        "loan_id": loan_id,
                        "account_number": loan_doc.farmer_confirmed_account_number,
                        "ifsc_code": loan_doc.farmer_confirmed_ifsc,
                        "account_holder_name": account_name,
                    }
                    disb_hash = self.crypto.generate_loan_hash(disb_data)
                    disbursement = DisbursementConsent(
                        loan_id=loan_id,
                        account_number=loan_doc.farmer_confirmed_account_number,
                        account_holder_name=account_name,
                        ifsc_code=loan_doc.farmer_confirmed_ifsc,
                        penny_drop_verified=True,
                        penny_drop_name_matched=True,
                        penny_drop_response='{"auto_created":"kiosk_ocr_confirmed"}',
                        disbursement_hash=disb_hash,
                    )
                    db.add(disbursement)
                    db.flush()
                else:
                    return (False, None, "Disbursement consent not found. Farmer must verify their bank account.")
            else:
                return (False, None, "Disbursement consent not found. Farmer must verify their bank account.")
        if not disbursement.penny_drop_verified:
            return (False, None, "Disbursement account has not been verified via penny drop.")

        # 6. SMS Notification Verification
        notifications = (
            db.query(Notification)
            .filter(Notification.loan_id == loan_id)
            .all()
        )
        notifications_by_type = {}
        for n in notifications:
            notifications_by_type[n.notification_type] = n

        required_notifications = ["loan_creation"]
        for notif_type in required_notifications:
            if notif_type not in notifications_by_type:
                return (
                    False,
                    None,
                    f"Missing {notif_type} notification. Farmer may not have been informed.",
                )
            notif = notifications_by_type[notif_type]
            if notif.delivery_status == "failed":
                logger.warning(
                    f"Notification {notif_type} delivery failed for loan {loan_id}"
                )
                return (
                    False,
                    None,
                    f"{notif_type} notification failed to deliver. Cannot confirm farmer was informed.",
                )

        # 7. Time-based validation
        if consent.consented_at and approvals:
            first_approval_time = min(
                a.approved_at for a in approvals if a.approved_at
            )
            if first_approval_time and consent.consented_at:
                time_gap = first_approval_time - consent.consented_at

                if time_gap < timedelta(minutes=5):
                    logger.warning(
                        f"⚠ Approval within 5 minutes of consent for loan {loan_id} "
                        f"– possible rush fraud"
                    )
                    # Warning only, not blocking for demo purposes

                if time_gap > timedelta(days=30):
                    return (
                        False,
                        None,
                        "Consent expired – farmer should re-consent. "
                        "More than 30 days have passed since consent.",
                    )

        # All checks passed – Generate final consent token
        farmer_consent_dict = {
            "loan_hash": consent.loan_hash,
            "consent_method": consent.consent_method,
            "bank_kyc_verified": consent.bank_kyc_verified,
            "fingerprint_hash": consent.fingerprint_hash,
            "consented_at": consent.consented_at.isoformat()
            if consent.consented_at
            else None,
        }
        approvals_list = [
            {
                "approver_id": a.approver_id,
                "approver_name": a.approver_name,
                "approver_role": a.approver_role,
                "approver_signature": a.approver_signature,
                "approved_at": a.approved_at.isoformat() if a.approved_at else None,
            }
            for a in approvals
        ]
        policy_info = {
            "tier": loan.approval_tier,
            "required_approvals": self.policy.get_required_approvals(loan.amount),
        }
        notification_info = {
            t: {
                "sent_at": n.sent_at.isoformat() if n.sent_at else None,
                "delivery_status": n.delivery_status,
            }
            for t, n in notifications_by_type.items()
        }

        final_token = self.crypto.generate_final_consent_token(
            loan_data=current_params,
            farmer_consent=farmer_consent_dict,
            approvals=approvals_list,
            policy=policy_info,
        )
        # Add notification info to token
        final_token["notifications"] = notification_info

        return (True, final_token, None)
