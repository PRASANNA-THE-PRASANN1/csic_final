"""
Integration test: Full CGE workflow.
Loan creation → farmer consent → manager approvals → execution → blockchain anchor.
"""

import os
import json
import tempfile
import pytest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.models.loan import Loan
from app.models.consent import FarmerConsent
from app.models.approval import Approval
from app.models.blockchain import BlockchainAnchor

from app.services.crypto_service import CryptoService
from app.services.policy_engine import PolicyEngine
from app.services.consent_engine import ConsentEngine
from app.services.blockchain_service import BlockchainService


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
    blockchain = BlockchainService(
        data_path=os.path.join(tmpdir, "chain.json")
    )

    yield db, crypto, policy, consent_engine, blockchain

    db.close()


class TestFullCGEWorkflow:
    def test_end_to_end_tier1(self, setup):
        """Complete flow for a tier-1 (≤₹1L) loan."""
        db, crypto, policy, consent_engine, blockchain = setup

        # 1. Create loan
        loan_params = {
            "farmer_id": "F001",
            "farmer_name": "Ramu Sharma",
            "amount": 50000.0,
            "tenure_months": 12,
            "interest_rate": 7.5,
            "purpose": "Crop cultivation",
        }
        loan_hash = crypto.generate_loan_hash(loan_params)
        tier = policy.determine_tier(50000.0)

        loan = Loan(
            loan_id="LN_TEST_001",
            farmer_id="F001",
            farmer_name="Ramu Sharma",
            farmer_mobile="9876543210",
            amount=50000.0,
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

        assert loan.loan_hash is not None
        assert len(loan.loan_hash) == 64
        assert loan.approval_tier == "tier_1"

        # 2. Farmer consent
        consent = consent_engine.create_farmer_consent(
            db=db,
            loan=loan,
            otp="123456",
        )
        assert consent.farmer_signature is not None
        assert consent.loan_hash == loan.loan_hash
        assert loan.status == "pending_approvals"

        # 3. Branch manager approval
        approval = consent_engine.create_manager_approval(
            db=db,
            loan=loan,
            approver_id="EMP101",
            approver_name="Suresh Kumar",
            approver_role="branch_manager",
            comments="Looks good",
        )
        assert approval.approver_signature is not None
        assert approval.loan_hash == loan.loan_hash
        assert loan.status == "ready_for_execution"

        # 4. Validate execution eligibility
        is_eligible, final_token, error = consent_engine.validate_execution_eligibility(
            db, "LN_TEST_001"
        )
        assert is_eligible is True
        assert final_token is not None
        assert "final_hash" in final_token
        assert error is None

        # 5. Anchor on blockchain
        anchor = blockchain.anchor_consent(db, "LN_TEST_001", final_token)
        assert anchor.consent_hash is not None
        assert anchor.block_number >= 1
        assert anchor.transaction_hash is not None

        # 6. Verify chain integrity
        chain_status = blockchain.verify_chain_integrity()
        assert chain_status["is_valid"] is True

    def test_end_to_end_tier2(self, setup):
        """Complete flow for a tier-2 loan requiring 2 approvals."""
        db, crypto, policy, consent_engine, blockchain = setup

        loan_params = {
            "farmer_id": "F002",
            "farmer_name": "Sita Devi",
            "amount": 300000.0,
            "tenure_months": 24,
            "interest_rate": 8.0,
            "purpose": "Tractor purchase",
        }
        loan_hash = crypto.generate_loan_hash(loan_params)
        tier = policy.determine_tier(300000.0)

        loan = Loan(
            loan_id="LN_TEST_002",
            farmer_id="F002",
            farmer_name="Sita Devi",
            farmer_mobile="9876543211",
            amount=300000.0,
            tenure_months=24,
            interest_rate=8.0,
            purpose="Tractor purchase",
            loan_hash=loan_hash,
            status="pending_farmer_consent",
            approval_tier=tier,
        )
        db.add(loan)
        db.commit()

        assert tier == "tier_2"

        consent_engine.create_farmer_consent(db, loan, "654321")
        assert loan.status == "pending_approvals"

        consent_engine.create_manager_approval(
            db, loan, "EMP101", "Suresh Kumar", "branch_manager"
        )
        assert loan.status == "pending_approvals"

        consent_engine.create_manager_approval(
            db, loan, "EMP201", "Priya Sharma", "regional_manager"
        )
        assert loan.status == "ready_for_execution"

    def test_tamper_detection(self, setup):
        """Modifying loan amount after consent should fail execution validation."""
        db, crypto, policy, consent_engine, blockchain = setup

        loan_params = {
            "farmer_id": "F003",
            "farmer_name": "Gopal Singh",
            "amount": 80000.0,
            "tenure_months": 6,
            "interest_rate": 7.0,
            "purpose": "Seeds and fertilizer",
        }
        loan_hash = crypto.generate_loan_hash(loan_params)

        loan = Loan(
            loan_id="LN_TEST_003",
            farmer_id="F003",
            farmer_name="Gopal Singh",
            farmer_mobile="9876543212",
            amount=80000.0,
            tenure_months=6,
            interest_rate=7.0,
            purpose="Seeds and fertilizer",
            loan_hash=loan_hash,
            status="pending_farmer_consent",
            approval_tier="tier_1",
        )
        db.add(loan)
        db.commit()

        consent_engine.create_farmer_consent(db, loan, "111111")
        consent_engine.create_manager_approval(
            db, loan, "EMP101", "Suresh Kumar", "branch_manager"
        )
        assert loan.status == "ready_for_execution"

        
        loan.amount = 180000.0
        db.commit()

        is_eligible, token, error = consent_engine.validate_execution_eligibility(
            db, "LN_TEST_003"
        )
        assert is_eligible is False
        assert "FRAUD DETECTED" in error
        assert "tampered" in error.lower()

    def test_duplicate_approval_rejected(self, setup):
        """Same approver cannot approve twice."""
        db, crypto, policy, consent_engine, blockchain = setup

        loan_params = {
            "farmer_id": "F004",
            "farmer_name": "Lata Kumari",
            "amount": 50000.0,
            "tenure_months": 12,
            "interest_rate": 7.5,
            "purpose": "Irrigation equipment",
        }
        loan_hash = crypto.generate_loan_hash(loan_params)

        loan = Loan(
            loan_id="LN_TEST_004",
            farmer_id="F004",
            farmer_name="Lata Kumari",
            farmer_mobile="9876543213",
            amount=50000.0,
            tenure_months=12,
            interest_rate=7.5,
            purpose="Irrigation equipment",
            loan_hash=loan_hash,
            status="pending_farmer_consent",
            approval_tier="tier_1",
        )
        db.add(loan)
        db.commit()

        consent_engine.create_farmer_consent(db, loan, "222222")

        consent_engine.create_manager_approval(
            db, loan, "EMP101", "Suresh Kumar", "branch_manager"
        )

        with pytest.raises(ValueError, match="already approved|not pending approvals"):
            consent_engine.create_manager_approval(
                db, loan, "EMP101", "Suresh Kumar", "branch_manager"
            )
