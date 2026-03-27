"""
KioskAnchorService — anchors the kiosk session consent evidence on the blockchain.
Called by KioskSessionService.complete_session().
"""

import json
import hashlib
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from app.models.loan import Loan
from app.models.kiosk_session import KioskSession
from app.services.kiosk_consent_service import KioskConsentService
from app.services.blockchain_service import BlockchainService


class KioskAnchorService:
    """Anchors the kiosk session on the blockchain after consent is obtained."""

    def __init__(self):
        self.consent_service = KioskConsentService()
        self.blockchain_service = BlockchainService()

    def anchor_kiosk_session(self, db: Session, loan_id: str):
        """Build consent token, hash it, anchor on blockchain, and update loan."""
        consent_token = self.consent_service.build_consent_token(db, loan_id)
        consent_str = json.dumps(consent_token, sort_keys=True, separators=(",", ":"), default=str)
        consent_hash = hashlib.sha256(consent_str.encode()).hexdigest()

        # Anchor on blockchain
        anchor = self.blockchain_service.anchor_consent(db, loan_id, consent_token)

        # Update loan
        loan = db.query(Loan).filter(Loan.loan_id == loan_id).first()
        if loan:
            loan.kiosk_phase_anchor_hash = anchor.transaction_hash
            loan.status = "kiosk_anchored"

        db.commit()

        # Transition to pending_clerk_review
        if loan:
            loan.status = "pending_clerk_review"
            db.commit()

        return {
            "kiosk_phase_anchor_hash": anchor.transaction_hash,
            "block_number": anchor.block_number,
            "consent_hash": consent_hash,
        }
