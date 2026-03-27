"""
Cryptographic service for the CGE system.
Uses Ed25519 for digital signatures and SHA-256 for hashing.
Private keys are encrypted at rest using Fernet (§2.3).
Keys are generated per-entity and stored on disk.
"""

import os
import json
import base64
import hashlib
from datetime import datetime, timezone
from typing import Dict, Tuple, Optional

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives import serialization
from cryptography.exceptions import InvalidSignature
from cryptography.fernet import Fernet
from dotenv import load_dotenv

load_dotenv(override=True)

KEYS_DIR = os.getenv("KEYS_DIR", "../data/keys")


class CryptoService:
    """Handles Ed25519 key generation, digital signing, verification, and hashing.
    Private keys are encrypted at rest using Fernet with MASTER_KEY."""

    def __init__(self, keys_dir: str = None):
        self.keys_dir = keys_dir or os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", KEYS_DIR)
        )
        os.makedirs(self.keys_dir, exist_ok=True)
        # Read MASTER_KEY fresh (not cached at module level) so .env changes are picked up
        load_dotenv(override=True)
        master_key = os.getenv("MASTER_KEY")
        self._fernet = None
        if master_key:
            try:
                self._fernet = Fernet(master_key.encode() if isinstance(master_key, str) else master_key)
            except (ValueError, Exception):
                # Invalid key format — generate a valid one and warn
                print(f"⚠ MASTER_KEY in .env is invalid. Generating a temporary Fernet key.")
                temp_key = Fernet.generate_key()
                self._fernet = Fernet(temp_key)

    # ── Hashing

    def generate_loan_hash(self, loan_data: dict) -> str:
        """
        Compute SHA-256 hash of canonical JSON representation of loan params.
        Keys are sorted for determinism.
        """
        canonical = json.dumps(loan_data, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    # ── Key Management (Fernet-encrypted at rest)

    def generate_key_pair(self, key_id: str) -> dict:
        """Generate an Ed25519 key pair. Private key encrypted with Fernet at rest."""
        private_key = Ed25519PrivateKey.generate()
        public_key = private_key.public_key()

        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        public_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )

        # Encrypt private key with Fernet before writing to disk (§2.3)
        if self._fernet:
            encrypted_pem = self._fernet.encrypt(private_pem)
            priv_path = os.path.join(self.keys_dir, f"{key_id}_private.pem.enc")
            with open(priv_path, "wb") as f:
                f.write(encrypted_pem)
        else:
            # Fallback: write plaintext if MASTER_KEY not configured
            priv_path = os.path.join(self.keys_dir, f"{key_id}_private.pem")
            with open(priv_path, "wb") as f:
                f.write(private_pem)

        pub_path = os.path.join(self.keys_dir, f"{key_id}_public.pem")
        with open(pub_path, "wb") as f:
            f.write(public_pem)

        return {
            "key_id": key_id,
            "public_key_path": pub_path,
            "private_key_path": priv_path,
            "public_key_pem": public_pem.decode("utf-8"),
        }

    def _ensure_key_pair(self, key_id: str):
        """Generate key pair if it doesn't exist yet."""
        enc_path = os.path.join(self.keys_dir, f"{key_id}_private.pem.enc")
        plain_path = os.path.join(self.keys_dir, f"{key_id}_private.pem")
        if not os.path.exists(enc_path) and not os.path.exists(plain_path):
            self.generate_key_pair(key_id)

    def _load_private_key(self, key_id: str):
        """Load private key, decrypting from Fernet-encrypted file if available."""
        enc_path = os.path.join(self.keys_dir, f"{key_id}_private.pem.enc")
        plain_path = os.path.join(self.keys_dir, f"{key_id}_private.pem")

        if os.path.exists(enc_path) and self._fernet:
            with open(enc_path, "rb") as f:
                encrypted_data = f.read()
            pem_bytes = self._fernet.decrypt(encrypted_data)
        elif os.path.exists(plain_path):
            with open(plain_path, "rb") as f:
                pem_bytes = f.read()
        else:
            raise FileNotFoundError(f"No private key found for {key_id}")

        return serialization.load_pem_private_key(pem_bytes, password=None)

    def delete_private_key(self, key_id: str):
        """Delete private key from disk after signing (§2.3 key deletion post-signing).
        Only the public key is retained for verification."""
        enc_path = os.path.join(self.keys_dir, f"{key_id}_private.pem.enc")
        plain_path = os.path.join(self.keys_dir, f"{key_id}_private.pem")
        for path in (enc_path, plain_path):
            if os.path.exists(path):
                os.remove(path)

    # ── Signing / Verification

    def sign_data(self, data: str, key_id: str) -> str:
        """Sign data string using Ed25519 private key. Returns base64 signature."""
        self._ensure_key_pair(key_id)
        private_key = self._load_private_key(key_id)
        signature = private_key.sign(data.encode("utf-8"))
        return base64.b64encode(signature).decode("utf-8")

    def verify_signature(self, data: str, signature_b64: str, key_id: str) -> bool:
        """Verify an Ed25519 signature. Returns True if valid."""
        pub_path = os.path.join(self.keys_dir, f"{key_id}_public.pem")
        if not os.path.exists(pub_path):
            return False

        with open(pub_path, "rb") as f:
            public_key = serialization.load_pem_public_key(f.read())

        try:
            signature = base64.b64decode(signature_b64)
            public_key.verify(signature, data.encode("utf-8"))
            return True
        except (InvalidSignature, Exception):
            return False

    # ── Consent Token Generation

    def generate_consent_token(
        self,
        loan_hash: str,
        farmer_signature: str,
        consent_method: str,
        metadata: Optional[dict] = None,
    ) -> dict:
        """Create a consent token containing all farmer consent details."""
        token = {
            "loan_hash": loan_hash,
            "farmer_signature": farmer_signature,
            "consent_method": consent_method,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "metadata": metadata or {},
        }
        token_str = json.dumps(token, sort_keys=True, separators=(",", ":"))
        token["token_hash"] = hashlib.sha256(token_str.encode("utf-8")).hexdigest()
        return token

    def generate_final_consent_token(
        self,
        loan_data: dict,
        farmer_consent: dict,
        approvals: list,
        policy: dict,
    ) -> dict:
        """Aggregate all consents into a master token for blockchain anchoring."""
        loan_hash = self.generate_loan_hash(loan_data)
        final = {
            "loan_hash": loan_hash,
            "farmer_consent": farmer_consent,
            "approvals": approvals,
            "policy": policy,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "version": "1.0",
        }
        final_str = json.dumps(final, sort_keys=True, separators=(",", ":"))
        final["final_hash"] = hashlib.sha256(final_str.encode("utf-8")).hexdigest()
        return final

    def get_data_hash(self, data: str) -> str:
        """Return SHA-256 hex digest of an arbitrary string."""
        return hashlib.sha256(data.encode("utf-8")).hexdigest()
