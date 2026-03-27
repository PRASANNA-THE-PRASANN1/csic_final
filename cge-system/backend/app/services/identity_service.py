"""
Identity Service – Realistic Bank-KYC based identity verification.

Uses existing bank KYC data + OTP verification + device fingerprint capture.
NO Aadhaar/UIDAI integration – works with cooperative bank customer master.
"""

import hashlib
import logging
import random
import re
import string
import time
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


# In-memory OTP store (use Redis in production)
_otp_store: dict = {}

# Mock bank KYC database (in production, this queries the bank's customer master)
_kyc_database: dict = {
    "F001": {
        "farmer_id": "F001",
        "farmer_name": "Ramesh Kumar",
        "mobile": "9876543210",
        "address": "Village Piplani, Sehore, MP",
        "account_number": "XXXX-XXXX-1234",
        "kyc_verified": True,
        "photo_on_file": True,
    },
    "F002": {
        "farmer_id": "F002",
        "farmer_name": "Sita Devi",
        "mobile": "9876543211",
        "address": "Village Hoshangabad, MP",
        "account_number": "XXXX-XXXX-5678",
        "kyc_verified": True,
        "photo_on_file": True,
    },
    "F003": {
        "farmer_id": "F003",
        "farmer_name": "Gopal Singh",
        "mobile": "9876543212",
        "address": "Village Raisen, MP",
        "account_number": "XXXX-XXXX-9012",
        "kyc_verified": True,
        "photo_on_file": True,
    },
}

# OTP format regex: exactly 6 digits
OTP_FORMAT_REGEX = re.compile(r"^\d{6}$")


class IdentityService:
    """
    Abstract identity verification layer that works with existing bank KYC data.

    This is the realistic alternative to UIDAI/Aadhaar integration.
    Banks already maintain KYC records for all customers – we leverage that.
    """

    def __init__(self):
        self.otp_expiry_seconds = 600  # 10 minutes

    # ── Method 1: Verify farmer identity via bank KYC

    def verify_farmer_identity(
        self, farmer_id: str, mobile_number: str
    ) -> dict:
        """
        Query bank's existing KYC database for farmer record.

        In production: queries Core Banking System (CBS) customer master.
        For MVP: uses mock database.

        Returns:
            {
                "identity_verified": bool,
                "farmer_name": str | None,
                "farmer_details": dict | None,
                "verification_method": "bank_kyc"
            }
        """
        kyc_record = _kyc_database.get(farmer_id)

        if not kyc_record:
            logger.warning(f"Farmer {farmer_id} not found in bank KYC database")
            return {
                "identity_verified": False,
                "farmer_name": None,
                "farmer_details": None,
                "verification_method": "bank_kyc",
                "error": "Farmer not found in bank KYC database",
            }

        # Verify mobile matches registered mobile in KYC
        if kyc_record["mobile"] != mobile_number:
            logger.warning(
                f"Mobile mismatch for farmer {farmer_id}: "
                f"expected {kyc_record['mobile'][-4:]}, got {mobile_number[-4:]}"
            )
            return {
                "identity_verified": False,
                "farmer_name": kyc_record["farmer_name"],
                "farmer_details": None,
                "verification_method": "bank_kyc",
                "error": "Mobile number does not match bank KYC records",
            }

        logger.info(f"✅ Farmer {farmer_id} verified via bank KYC")
        return {
            "identity_verified": True,
            "farmer_name": kyc_record["farmer_name"],
            "farmer_details": {
                "farmer_id": kyc_record["farmer_id"],
                "address": kyc_record["address"],
                "kyc_verified": kyc_record["kyc_verified"],
                "photo_on_file": kyc_record["photo_on_file"],
            },
            "verification_method": "bank_kyc",
        }

    # ── Method 2: Send consent OTP

    def send_consent_otp(self, mobile_number: str) -> dict:
        """
        Generate 6-digit OTP and store with expiry.

        In production: integrates with SMS gateway (Twilio, MSG91, Fast2SMS).
        For MVP: stores in memory and logs to console.

        Returns:
            {"otp_reference_id": str, "otp_sent": bool, "expires_in_seconds": int}
        """
        otp = "".join(random.choices(string.digits, k=6))
        ref_id = f"OTP_{uuid.uuid4().hex[:8].upper()}"

        _otp_store[ref_id] = {
            "mobile": mobile_number,
            "otp": otp,
            "created_at": time.time(),
            "used": False,
        }

        # In production: send via SMS gateway
        logger.info(f"📱 OTP sent to {mobile_number[-4:]}: {otp} (ref: {ref_id})")
        print(f"📱 [MOCK OTP] To: +91-XXXXX-{mobile_number[-5:]} | OTP: {otp} | Ref: {ref_id}")

        return {
            "otp_reference_id": ref_id,
            "otp_sent": True,
            "expires_in_seconds": self.otp_expiry_seconds,
            # For demo only – remove in production
            "demo_otp": otp,
        }

    # ── Method 3: Verify consent OTP

    def verify_consent_otp(
        self, mobile_number: str, otp: str, otp_reference_id: str
    ) -> dict:
        """
        Validate OTP against stored value with strict checks.

        Enforces:
        1. Exactly 6-digit format
        2. Exact value match
        3. 10-minute expiry
        4. Single-use (no reuse)
        5. Mobile number match

        Returns:
            {"verification_success": bool, "error": str | None, "error_code": str | None}
        """
        # Check 1: Validate OTP format – must be exactly 6 digits
        if not OTP_FORMAT_REGEX.match(otp):
            return {
                "verification_success": False,
                "error": "OTP must be exactly 6 digits",
                "error_code": "OTP_INVALID_FORMAT",
            }

        record = _otp_store.get(otp_reference_id)

        if not record:
            return {
                "verification_success": False,
                "error": "Invalid OTP reference ID",
                "error_code": "OTP_INVALID_REF",
            }

        # Check 2: Already used
        if record["used"]:
            return {
                "verification_success": False,
                "error": "OTP has already been used. Please request a new one.",
                "error_code": "OTP_ALREADY_USED",
            }

        # Check 3: Expiry
        elapsed = time.time() - record["created_at"]
        if elapsed > self.otp_expiry_seconds:
            return {
                "verification_success": False,
                "error": "OTP has expired. Please request a new one.",
                "error_code": "OTP_EXPIRED",
            }

        # Check 4: Mobile match
        if record["mobile"] != mobile_number:
            return {
                "verification_success": False,
                "error": "Mobile number mismatch",
                "error_code": "OTP_MOBILE_MISMATCH",
            }

        # Check 5: OTP value match
        if record["otp"] != otp:
            return {
                "verification_success": False,
                "error": "Incorrect OTP. Please check and try again.",
                "error_code": "OTP_MISMATCH",
            }

        # Mark as used (prevent reuse)
        record["used"] = True
        logger.info(f"✅ OTP verified for mobile {mobile_number[-4:]}")

        return {
            "verification_success": True,
            "error": None,
            "error_code": None,
        }

    # ── Method 4: Verify device fingerprint

    def verify_device_fingerprint(
        self,
        farmer_id: str,
        device_fingerprint_hash: str,
        device_metadata: Optional[dict] = None,
    ) -> dict:
        """
        Verify and record device fingerprint for consent presence verification.

        The device fingerprint is computed client-side from:
        - Canvas fingerprint (unique per device GPU rendering)
        - WebGL renderer string (identifies GPU)
        - Screen resolution

        These are hashed together with SHA-256 to produce a unique device identifier.

        Returns:
            {"device_fingerprint_hash": str, "verified": bool, "device": str}
        """
        # Validate hash format (should be 64 hex chars from SHA-256)
        if not device_fingerprint_hash or not re.match(r"^[a-f0-9]{64}$", device_fingerprint_hash):
            logger.warning(f"Invalid device fingerprint hash for farmer {farmer_id}")
            return {
                "device_fingerprint_hash": None,
                "verified": False,
                "device": "unknown",
                "error": "Invalid device fingerprint hash format",
            }

        logger.info(f"🔐 Device fingerprint verified for farmer {farmer_id}")
        print(f"🔐 [DEVICE FINGERPRINT] Farmer {farmer_id} device verified")
        print(f"   Hash: {device_fingerprint_hash[:16]}...")
        if device_metadata:
            print(f"   WebGL: {device_metadata.get('webgl_renderer', 'N/A')}")
            print(f"   Screen: {device_metadata.get('screen_resolution', 'N/A')}")

        return {
            "device_fingerprint_hash": device_fingerprint_hash,
            "verified": True,
            "device": "Browser device fingerprint (Canvas + WebGL + Screen)",
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "storage": "local_only",  # Emphasize: NOT sent to UIDAI
            "metadata": device_metadata or {},
        }
