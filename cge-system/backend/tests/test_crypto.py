"""
Tests for the CryptoService (Ed25519).
"""

import os
import tempfile
import pytest

from app.services.crypto_service import CryptoService


@pytest.fixture
def crypto():
    """Create a CryptoService with a temporary keys directory."""
    tmpdir = tempfile.mkdtemp()
    return CryptoService(keys_dir=tmpdir)


class TestHashGeneration:
    def test_loan_hash_deterministic(self, crypto):
        """Same loan data must always produce the same hash."""
        data = {
            "farmer_id": "F001",
            "farmer_name": "Ramu",
            "amount": 100000,
            "tenure_months": 12,
            "interest_rate": 7.5,
            "purpose": "Crop cultivation",
        }
        h1 = crypto.generate_loan_hash(data)
        h2 = crypto.generate_loan_hash(data)
        assert h1 == h2
        assert len(h1) == 64  # SHA-256 hex

    def test_hash_changes_on_tampering(self, crypto):
        """Even a tiny change must produce a completely different hash."""
        data = {
            "farmer_id": "F001",
            "farmer_name": "Ramu",
            "amount": 100000,
            "tenure_months": 12,
            "interest_rate": 7.5,
            "purpose": "Crop cultivation",
        }
        h1 = crypto.generate_loan_hash(data)

        tampered = {**data, "amount": 100001}
        h2 = crypto.generate_loan_hash(tampered)
        assert h1 != h2


class TestEd25519Signing:
    def test_key_pair_generation(self, crypto):
        """Should create PEM files for a key pair."""
        result = crypto.generate_key_pair("test_entity")
        assert os.path.exists(result["private_key_path"])
        assert os.path.exists(result["public_key_path"])
        assert "BEGIN PUBLIC KEY" in result["public_key_pem"]

    def test_sign_and_verify(self, crypto):
        """Signature must verify successfully with the correct key."""
        key_id = "farmer_F001"
        data = "abc123hash"
        signature = crypto.sign_data(data, key_id)
        assert isinstance(signature, str)
        assert crypto.verify_signature(data, signature, key_id) is True

    def test_tampered_data_fails(self, crypto):
        """Changing the data must invalidate the signature."""
        key_id = "farmer_F002"
        data = "original_hash"
        signature = crypto.sign_data(data, key_id)
        assert crypto.verify_signature("tampered_hash", signature, key_id) is False

    def test_wrong_key_fails(self, crypto):
        """Using a different key must invalidate the signature."""
        sig = crypto.sign_data("data", "key_A")
        # key_B has a different key pair
        assert crypto.verify_signature("data", sig, "key_B") is False


class TestConsentTokens:
    def test_consent_token_has_hash(self, crypto):
        """Consent token must include a token_hash field."""
        token = crypto.generate_consent_token(
            loan_hash="abc123",
            farmer_signature="sig456",
            consent_method="mobile_otp",
        )
        assert "token_hash" in token
        assert token["loan_hash"] == "abc123"

    def test_final_consent_token(self, crypto):
        """Final token must aggregate farmer consent and all approvals."""
        final = crypto.generate_final_consent_token(
            loan_data={"farmer_id": "F001", "amount": 100000},
            farmer_consent={"loan_hash": "h1", "farmer_signature": "s1"},
            approvals=[
                {"approver_id": "EMP101", "approver_role": "branch_manager"}
            ],
            policy={"tier": "tier_1"},
        )
        assert "final_hash" in final
        assert final["version"] == "1.0"
