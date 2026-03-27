"""
Policy engine for the CGE system.
Determines required approval tiers based on loan amount.
Tier thresholds use Indian Rupee amounts.
"""

from typing import List, Dict, Any, Tuple


# Approval hierarchy
VALID_ROLES = ["branch_manager", "credit_manager", "ceo", "board_member"]

# Tier-based approval policies
APPROVAL_POLICIES = {
    "tier_1": {
        "min_amount": 0,
        "max_amount": 100_000,
        "required_approvals": [{"role": "branch_manager", "count": 1}],
        "max_processing_days": 2,
        "description": "Small loans (up to ₹1,00,000)",
    },
    "tier_2": {
        "min_amount": 100_001,
        "max_amount": 500_000,
        "required_approvals": [
            {"role": "branch_manager", "count": 1},
            {"role": "credit_manager", "count": 1},
        ],
        "max_processing_days": 5,
        "description": "Medium loans (₹1,00,001 – ₹5,00,000)",
    },
    "tier_3": {
        "min_amount": 500_001,
        "max_amount": 2_000_000,
        "required_approvals": [
            {"role": "branch_manager", "count": 1},
            {"role": "credit_manager", "count": 1},
            {"role": "ceo", "count": 1},
        ],
        "max_processing_days": 7,
        "description": "Large loans (₹5,00,001 – ₹20,00,000)",
    },
    "tier_4": {
        "min_amount": 2_000_001,
        "max_amount": 10_000_000,
        "required_approvals": [
            {"role": "branch_manager", "count": 1},
            {"role": "credit_manager", "count": 1},
            {"role": "ceo", "count": 1},
            {"role": "board_member", "count": 1},
        ],
        "max_processing_days": 14,
        "description": "Very large loans (₹20,00,001 – ₹1,00,00,000)",
        "requires_committee": True,
    },
}


class PolicyEngine:
    """Evaluates loan applications against the tier-based approval policy."""

    def __init__(self, policies: Dict[str, Any] = None):
        self.policies = policies or APPROVAL_POLICIES

    # ── Tier determination

    def determine_tier(self, loan_amount: float) -> str:
        """Return the tier key (tier_1 .. tier_4) for a given loan amount."""
        for tier_key, tier in self.policies.items():
            if tier["min_amount"] <= loan_amount <= tier["max_amount"]:
                return tier_key
        if loan_amount > 10_000_000:
            raise ValueError(
                f"Loan amount ₹{loan_amount:,.0f} exceeds maximum ₹1,00,00,000"
            )
        raise ValueError(f"Invalid loan amount: {loan_amount}")

    def get_tier_info(self, loan_amount: float) -> dict:
        """Return full tier details for a loan amount."""
        tier_key = self.determine_tier(loan_amount)
        tier = self.policies[tier_key]
        return {"tier": tier_key, **tier}

    # ── Required approvals

    def get_required_approvals(self, loan_amount: float) -> List[Dict[str, Any]]:
        """Return list of required approval role/count dicts."""
        tier_key = self.determine_tier(loan_amount)
        return self.policies[tier_key]["required_approvals"]

    def get_required_roles(self, loan_amount: float) -> List[str]:
        """Return flat list of required role names."""
        return [r["role"] for r in self.get_required_approvals(loan_amount)]

    # ── Validation

    def validate_approvals(
        self, loan_amount: float, approvals_list: List[Dict]
    ) -> Tuple[bool, str]:
        """
        Check whether all required approvals have been collected.
        approvals_list: list of dicts with at least 'approver_role' and 'approver_id'.
        Returns (is_valid, message).
        """
        required = self.get_required_approvals(loan_amount)

        # Check each requirement
        for req in required:
            role = req["role"]
            needed = req["count"]
            # Unique approvers for this role
            role_approvers = set()
            for a in approvals_list:
                if a.get("approver_role") == role:
                    role_approvers.add(a.get("approver_id", a.get("approver_name")))
            if len(role_approvers) < needed:
                return (
                    False,
                    f"Missing {role} approval ({len(role_approvers)}/{needed})",
                )

        # Check for duplicate approvals (same person approving twice)
        seen = set()
        for a in approvals_list:
            key = (a.get("approver_id"), a.get("loan_id"))
            if key in seen:
                return (False, f"Duplicate approval from {a.get('approver_id')}")
            seen.add(key)

        return (True, "All required approvals collected")

    def get_missing_approvals(
        self, loan_amount: float, current_approvals: List[Dict]
    ) -> List[Dict]:
        """Return list of still-needed approvals."""
        required = self.get_required_approvals(loan_amount)
        missing = []

        for req in required:
            role = req["role"]
            needed = req["count"]
            current_count = sum(
                1 for a in current_approvals if a.get("approver_role") == role
            )
            if current_count < needed:
                missing.append(
                    {"role": role, "needed": needed - current_count}
                )

        return missing

    # ── Role validation

    def is_role_required(self, loan_amount: float, role: str) -> bool:
        """Check if a specific role is required for this loan amount."""
        return role in self.get_required_roles(loan_amount)

    def validate_loan(self, amount: float, purpose: str) -> Dict[str, Any]:
        """Basic loan validation."""
        violations = []
        warnings = []

        if amount <= 0:
            violations.append("Loan amount must be positive")
        if amount > 10_000_000:
            violations.append(f"Loan amount ₹{amount:,.0f} exceeds maximum ₹1,00,00,000")
        if len(purpose.strip()) < 5:
            warnings.append("Loan purpose description is very short")

        tier_info = None
        if not violations:
            try:
                tier_info = self.get_tier_info(amount)
            except ValueError as e:
                violations.append(str(e))

        return {
            "is_valid": len(violations) == 0,
            "violations": violations,
            "warnings": warnings,
            "tier_info": tier_info,
        }
