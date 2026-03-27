"""
Fraud scenario tests for CGE system.
Tests the three critical fraud detection capabilities:
1. Database tampering detection
2. Forged approval detection
3. Missing notification blocking execution
"""

import os
import tempfile
import pytest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.models.loan import Loan
from app.models.consent import FarmerConsent
from app.models.approval import Approval
from app.models.notification import Notification
from app.models.disbursement import DisbursementConsent
from app.models.declaration import FarmerDeclaration
from app.models.blockchain import BlockchainAnchor
from app.models.user import User

from app.services.crypto_service import CryptoService
from app.services.policy_engine import PolicyEngine
from app.services.consent_engine import ConsentEngine
from app.services.notification_service import NotificationService


@pytest.fixture
def setup():
    """Create in-memory DB with all services."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    tmpdir = tempfile.mkdtemp()
    crypto = CryptoService(keys_dir=os.path.join(tmpdir, "keys"))
    policy = PolicyEngine()
    consent_engine = ConsentEngine(crypto, policy)
    notification_service = NotificationService()

    yield db, crypto, policy, consent_engine, notification_service

    db.close()


def _create_loan_with_consent_and_approvals(
    db, crypto, policy, consent_engine, notification_service,
    loan_id="LN_FRAUD_001",
    farmer_id="F001",
    amount=50000.0,
    send_notifications=True,
):
    """Helper: create loan → consent → approval → disbursement consent → ready for execution."""
    import hashlib

    loan_params = {
        "farmer_id": farmer_id,
        "farmer_name": "Test Farmer",
        "amount": amount,
        "tenure_months": 12,
        "interest_rate": 7.5,
        "purpose": "Crop cultivation",
    }
    loan_hash = crypto.generate_loan_hash(loan_params)
    tier = policy.determine_tier(amount)

    loan = Loan(
        loan_id=loan_id,
        farmer_id=farmer_id,
        farmer_name="Test Farmer",
        farmer_mobile="9876543210",
        amount=amount,
        tenure_months=12,
        interest_rate=7.5,
        purpose="Crop cultivation",
        loan_hash=loan_hash,
        status="pending_farmer_consent",
        approval_tier=tier,
        created_by="EMP001",
    )
    db.add(loan)
    db.commit()

    if send_notifications:
        notification_service.send_loan_creation_notification(
            db=db,
            farmer_mobile="9876543210",
            loan_details={
                "amount": amount,
                "purpose": "Crop cultivation",
                "loan_id": loan_id,
            },
        )

    consent_engine.create_farmer_consent(
        db=db, loan=loan, otp="123456",
        bank_kyc_verified=True,
        fingerprint_hash="a" * 64,
    )

    if send_notifications:
        notification_service.send_consent_confirmation_notification(
            db=db,
            farmer_mobile="9876543210",
            loan_details={
                "amount": amount,
                "loan_id": loan_id,
                "tenure_months": 12,
                "interest_rate": 7.5,
            },
        )

    consent_engine.create_manager_approval(
        db=db,
        loan=loan,
        approver_id="EMP101",
        approver_name="Suresh Manager",
        approver_role="branch_manager",
    )

    disb_data = f"{loan_id}|1234567890|{farmer_id}|50000"
    disb_hash = hashlib.sha256(disb_data.encode()).hexdigest()
    disb = DisbursementConsent(
        loan_id=loan_id,
        account_number="1234567890",
        account_holder_name="Test Farmer",
        ifsc_code="DCCB0001234",
        penny_drop_verified=True,
        penny_drop_name_matched=True,
        penny_drop_response='{"status": "success", "name_match": true}',
        disbursement_hash=disb_hash,
    )
    db.add(disb)
    db.commit()

    return loan


class TestDatabaseTamperingDetection:
    """Fraud Type: Insider modifies loan amount after all signatures collected."""

    def test_amount_tampered_after_consent(self, setup):
        """Changing the loan amount after consent should be detected."""
        db, crypto, policy, consent_engine, notification = setup

        loan = _create_loan_with_consent_and_approvals(
            db, crypto, policy, consent_engine, notification,
            loan_id="LN_TAMPER_001",
        )
        assert loan.status == "ready_for_execution"

        loan.amount = 150000.0
        db.commit()

        is_eligible, token, error = consent_engine.validate_execution_eligibility(
            db, "LN_TAMPER_001"
        )
        assert is_eligible is False
        assert "FRAUD DETECTED" in error
        assert "tampered" in error.lower()

    def test_purpose_tampered_after_consent(self, setup):
        """Changing the loan purpose after consent should be detected."""
        db, crypto, policy, consent_engine, notification = setup

        loan = _create_loan_with_consent_and_approvals(
            db, crypto, policy, consent_engine, notification,
            loan_id="LN_TAMPER_002",
        )

        loan.purpose = "Personal use"
        db.commit()

        is_eligible, token, error = consent_engine.validate_execution_eligibility(
            db, "LN_TAMPER_002"
        )
        assert is_eligible is False
        assert "FRAUD DETECTED" in error

    def test_farmer_name_tampered(self, setup):
        """Changing farmer details after consent should be detected."""
        db, crypto, policy, consent_engine, notification = setup

        loan = _create_loan_with_consent_and_approvals(
            db, crypto, policy, consent_engine, notification,
            loan_id="LN_TAMPER_003",
        )

        loan.farmer_id = "F999"
        db.commit()

        is_eligible, token, error = consent_engine.validate_execution_eligibility(
            db, "LN_TAMPER_003"
        )
        assert is_eligible is False
        assert "FRAUD DETECTED" in error


class TestForgedApprovalDetection:
    """Fraud Type: Insider forges a manager approval entry in the database."""

    def test_forged_signature_detected(self, setup):
        """A manually inserted approval with invalid signature should be rejected."""
        db, crypto, policy, consent_engine, notification = setup

        loan_params = {
            "farmer_id": "F002",
            "farmer_name": "Forged Test",
            "amount": 300000.0,
            "tenure_months": 24,
            "interest_rate": 8.0,
            "purpose": "Tractor purchase",
        }
        loan_hash = crypto.generate_loan_hash(loan_params)

        loan = Loan(
            loan_id="LN_FORGE_001",
            farmer_id="F002",
            farmer_name="Forged Test",
            farmer_mobile="9876543211",
            amount=300000.0,
            tenure_months=24,
            interest_rate=8.0,
            purpose="Tractor purchase",
            loan_hash=loan_hash,
            status="pending_farmer_consent",
            approval_tier="tier_2",
        )
        db.add(loan)
        db.commit()

        notification.send_loan_creation_notification(
            db=db,
            farmer_mobile="9876543211",
            loan_details={"amount": 300000.0, "purpose": "Tractor purchase", "loan_id": "LN_FORGE_001"},
        )

        consent_engine.create_farmer_consent(db=db, loan=loan, otp="654321")

        notification.send_consent_confirmation_notification(
            db=db,
            farmer_mobile="9876543211",
            loan_details={"amount": 300000.0, "loan_id": "LN_FORGE_001", "tenure_months": 24, "interest_rate": 8.0},
        )

        consent_engine.create_manager_approval(
            db, loan, "EMP101", "Branch Manager", "branch_manager"
        )

        forged_approval = Approval(
            loan_id="LN_FORGE_001",
            approver_id="EMP999",
            approver_name="Ghost Manager",
            approver_role="regional_manager",
            loan_hash=loan_hash,
            approver_signature="FORGED_INVALID_SIGNATURE_BASE64",
            comments="Forged",
        )
        db.add(forged_approval)
        loan.status = "ready_for_execution"
        db.commit()

        is_eligible, token, error = consent_engine.validate_execution_eligibility(
            db, "LN_FORGE_001"
        )
        assert is_eligible is False
        assert "verification failed" in error.lower() or "signature" in error.lower()


class TestMissingNotificationBlocksExecution:
    """Fraud Type: Notifications not sent – farmer may not have been informed."""

    def test_no_notifications_blocks_execution(self, setup):
        """Execution should be blocked if SMS notifications were not sent."""
        db, crypto, policy, consent_engine, notification = setup

        loan = _create_loan_with_consent_and_approvals(
            db, crypto, policy, consent_engine, notification,
            loan_id="LN_NOTIF_001",
            send_notifications=False,
        )
        assert loan.status == "ready_for_execution"

        is_eligible, token, error = consent_engine.validate_execution_eligibility(
            db, "LN_NOTIF_001"
        )
        assert is_eligible is False
        assert "notification" in error.lower() or "notif" in error.lower()

    def test_missing_consent_notification_blocks(self, setup):
        """Only loan creation notification sent – consent confirmation missing."""
        import hashlib
        db, crypto, policy, consent_engine, notification_service = setup

        loan_params = {
            "farmer_id": "F003",
            "farmer_name": "Partial Test",
            "amount": 50000.0,
            "tenure_months": 12,
            "interest_rate": 7.5,
            "purpose": "Seeds",
        }
        loan_hash = crypto.generate_loan_hash(loan_params)

        loan = Loan(
            loan_id="LN_NOTIF_002",
            farmer_id="F003",
            farmer_name="Partial Test",
            farmer_mobile="9876543212",
            amount=50000.0,
            tenure_months=12,
            interest_rate=7.5,
            purpose="Seeds",
            loan_hash=loan_hash,
            status="pending_farmer_consent",
            approval_tier="tier_1",
            created_by="EMP001",
        )
        db.add(loan)
        db.commit()

        notification_service.send_loan_creation_notification(
            db=db,
            farmer_mobile="9876543212",
            loan_details={"amount": 50000.0, "purpose": "Seeds", "loan_id": "LN_NOTIF_002"},
        )

        consent_engine.create_farmer_consent(db=db, loan=loan, otp="333333")

        consent_engine.create_manager_approval(
            db, loan, "EMP101", "Manager", "branch_manager"
        )

        disb_data = "LN_NOTIF_002|1234567890|F003|50000"
        disb_hash = hashlib.sha256(disb_data.encode()).hexdigest()
        disb = DisbursementConsent(
            loan_id="LN_NOTIF_002",
            account_number="1234567890",
            account_holder_name="Partial Test",
            ifsc_code="DCCB0001234",
            penny_drop_verified=True,
            penny_drop_name_matched=True,
            penny_drop_response='{"status": "success"}',
            disbursement_hash=disb_hash,
        )
        db.add(disb)
        db.commit()

        assert loan.status == "ready_for_execution"

        is_eligible, token, error = consent_engine.validate_execution_eligibility(
            db, "LN_NOTIF_002"
        )
        assert is_eligible is False
        assert "consent_confirmation" in error.lower() or "notification" in error.lower()

