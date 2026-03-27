"""
Penny Drop Service – Mock implementation for bank account verification.
In production, this would integrate with Cashfree/Razorpay/NPCI APIs.
For the demo, it simulates account ownership verification via fuzzy name matching
against the farmer's registered name from the loan record.
"""

import re
import logging
from typing import Dict, Any

from rapidfuzz import fuzz

logger = logging.getLogger(__name__)

# Similarity threshold: account holder name must be at least 75% similar
NAME_MATCH_THRESHOLD = 75


class PennyDropService:
    """
    Verifies bank account ownership by performing a small (₹1) deposit
    and checking the account holder name via bank response.
    """

    def __init__(self):
        self.is_mock = True  # Flag to indicate this is a mock service

    def verify_account_ownership(
        self,
        account_number: str,
        ifsc_code: str,
        expected_name: str,
        farmer_registered_name: str = "",
    ) -> Dict[str, Any]:
        """
        Mock penny-drop verification.
        Simulates a real API call by comparing the expected name (entered by the clerk)
        against the farmer's registered name from the loan record.

        In production, this would:
        1. Call bank API with account_number + IFSC
        2. Deposit ₹1 to the account
        3. Retrieve the account holder name from the bank's response
        4. Compare with the expected farmer name

        Args:
            account_number: Bank account number entered by clerk
            ifsc_code: IFSC code entered by clerk
            expected_name: Account holder name entered by clerk
            farmer_registered_name: The farmer's name from the loan record (used as
                                    the "bank response" in mock mode)

        Returns:
            {
                "verified": bool,
                "name_matched": bool,
                "account_holder_name": str,
                "account_status": str,
                "ifsc_valid": bool,
                "bank_name": str,
                "similarity_score": float,
                "mock": bool,
            }
        """
        # Validate IFSC format (11 chars: 4 alpha + 0 + 6 alphanumeric)
        ifsc_valid = bool(re.match(r"^[A-Z]{4}0[A-Z0-9]{6}$", ifsc_code.upper()))

        # Validate account number (8-18 digits)
        account_valid = bool(re.match(r"^\d{8,18}$", account_number))

        if not ifsc_valid or not account_valid:
            return {
                "verified": False,
                "name_matched": False,
                "account_holder_name": "",
                "account_status": "invalid_details",
                "ifsc_valid": ifsc_valid,
                "bank_name": "",
                "similarity_score": 0.0,
                "mock": True,
            }

        # Mock: simulate bank lookup — the "bank" returns the farmer's registered name
        # In production, the bank returns the real account holder name
        found_name = farmer_registered_name if farmer_registered_name else expected_name

        # Fuzzy name matching using rapidfuzz
        similarity_score = self._fuzzy_name_match(expected_name, found_name)
        name_matched = similarity_score >= NAME_MATCH_THRESHOLD

        if not name_matched:
            logger.warning(
                f"⚠ Penny drop name mismatch: expected='{expected_name}', "
                f"found='{found_name}', similarity={similarity_score:.1f}%"
            )

        # Derive mock bank name from IFSC prefix
        bank_prefix = ifsc_code[:4].upper()
        bank_names = {
            "SBIN": "State Bank of India",
            "HDFC": "HDFC Bank",
            "ICIC": "ICICI Bank",
            "PUNB": "Punjab National Bank",
            "BKID": "Bank of India",
            "UBIN": "Union Bank of India",
            "CNRB": "Canara Bank",
            "BARB": "Bank of Baroda",
            "IOBA": "Indian Overseas Bank",
            "UCBA": "UCO Bank",
        }
        bank_name = bank_names.get(bank_prefix, f"{bank_prefix} Bank (Cooperative)")

        return {
            "verified": name_matched,
            "name_matched": name_matched,
            "account_holder_name": found_name,
            "account_status": "active" if name_matched else "name_mismatch",
            "ifsc_valid": True,
            "bank_name": bank_name,
            "similarity_score": round(similarity_score, 2),
            "mock": True,
        }

    @staticmethod
    def _fuzzy_name_match(name1: str, name2: str) -> float:
        """
        Fuzzy name comparison using rapidfuzz.
        Returns a similarity score from 0 to 100.
        Uses fuzz.ratio() for full string comparison.
        """
        def normalize(name: str) -> str:
            return " ".join(name.strip().lower().split())

        n1 = normalize(name1)
        n2 = normalize(name2)

        # Use rapidfuzz ratio for robust comparison
        return fuzz.ratio(n1, n2)
