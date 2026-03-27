"""
Tests for the PolicyEngine (4-tier approval system).
"""

import pytest
from app.services.policy_engine import PolicyEngine


@pytest.fixture
def policy():
    return PolicyEngine()


class TestTierDetermination:
    def test_tier_1(self, policy):
        assert policy.determine_tier(50_000) == "tier_1"
        assert policy.determine_tier(100_000) == "tier_1"

    def test_tier_2(self, policy):
        assert policy.determine_tier(100_001) == "tier_2"
        assert policy.determine_tier(300_000) == "tier_2"
        assert policy.determine_tier(500_000) == "tier_2"

    def test_tier_3(self, policy):
        assert policy.determine_tier(500_001) == "tier_3"
        assert policy.determine_tier(1_000_000) == "tier_3"
        assert policy.determine_tier(2_000_000) == "tier_3"

    def test_tier_4(self, policy):
        assert policy.determine_tier(2_000_001) == "tier_4"
        assert policy.determine_tier(5_000_000) == "tier_4"
        assert policy.determine_tier(10_000_000) == "tier_4"

    def test_exceeds_max(self, policy):
        with pytest.raises(ValueError, match="exceeds maximum"):
            policy.determine_tier(10_000_001)


class TestRequiredApprovals:
    def test_tier_1_needs_branch_only(self, policy):
        roles = policy.get_required_roles(50_000)
        assert roles == ["branch_manager"]

    def test_tier_2_needs_branch_and_regional(self, policy):
        roles = policy.get_required_roles(300_000)
        assert "branch_manager" in roles
        assert "regional_manager" in roles
        assert len(roles) == 2

    def test_tier_3_needs_three(self, policy):
        roles = policy.get_required_roles(1_000_000)
        assert len(roles) == 3
        assert "credit_head" in roles

    def test_tier_4_needs_all_four(self, policy):
        roles = policy.get_required_roles(5_000_000)
        assert len(roles) == 4
        assert "zonal_head" in roles


class TestApprovalValidation:
    def test_all_approvals_met(self, policy):
        approvals = [
            {"approver_role": "branch_manager", "approver_id": "EMP101"},
        ]
        is_valid, msg = policy.validate_approvals(50_000, approvals)
        assert is_valid is True

    def test_missing_approval(self, policy):
        approvals = [
            {"approver_role": "branch_manager", "approver_id": "EMP101"},
        ]
        is_valid, msg = policy.validate_approvals(300_000, approvals)
        assert is_valid is False
        assert "regional_manager" in msg

    def test_missing_approvals_list(self, policy):
        approvals = [
            {"approver_role": "branch_manager", "approver_id": "EMP101"},
        ]
        missing = policy.get_missing_approvals(300_000, approvals)
        assert len(missing) == 1
        assert missing[0]["role"] == "regional_manager"


class TestLoanValidation:
    def test_valid_loan(self, policy):
        result = policy.validate_loan(50_000, "Crop cultivation expenses")
        assert result["is_valid"] is True
        assert result["tier_info"]["tier"] == "tier_1"

    def test_zero_amount(self, policy):
        result = policy.validate_loan(0, "Something")
        assert result["is_valid"] is False

    def test_exceeding_max(self, policy):
        result = policy.validate_loan(20_000_000, "Big purchase")
        assert result["is_valid"] is False
