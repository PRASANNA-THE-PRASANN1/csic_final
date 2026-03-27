"""
Tests for the IVR consent flow.
- TwiML generation tests (pure unit tests, no DB)
- IVR timeout logic tests (pure unit tests)
- IVR webhook tests (use FastAPI TestClient + real app DB)
"""

import os
import sys
import pytest
from datetime import datetime, timezone, timedelta
from xml.etree import ElementTree

# Ensure backend is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ══════════════════════════════════════════════════════════════════════
#  1. UNIT TESTS — No DB required
# ══════════════════════════════════════════════════════════════════════

class TestTwiMLGeneration:
    """Tests for the IVR service TwiML builder."""

    def test_twiml_has_gather_elements(self):
        """TwiML should have multiple Gather elements for retry loop."""
        from app.services.ivr_service import IVRService
        svc = IVRService()
        twiml = svc._build_voice_twiml("LN_TEST", 50000.0)

        root = ElementTree.fromstring(twiml)
        gathers = root.findall("Gather")
        assert len(gathers) >= 2, f"Expected at least 2 Gather elements, got {len(gathers)}"

    def test_twiml_uses_hindi_voice(self):
        """TwiML should use Polly.Aditi for Hindi."""
        from app.services.ivr_service import IVRService
        svc = IVRService()
        twiml = svc._build_voice_twiml("LN_TEST", 50000.0)

        assert "Polly.Aditi" in twiml
        assert 'language="hi-IN"' in twiml

    def test_twiml_contains_loan_amount(self):
        """TwiML should mention the loan amount."""
        from app.services.ivr_service import IVRService
        svc = IVRService()
        twiml = svc._build_voice_twiml("LN_TEST", 75000.0)

        assert "75000" in twiml

    def test_twiml_has_webhook_url(self):
        """TwiML Gather action should point to the webhook."""
        from app.services.ivr_service import IVRService
        svc = IVRService()
        twiml = svc._build_voice_twiml("LN_TEST", 50000.0)

        assert "/api/ivr/webhook?loan_id=LN_TEST" in twiml

    def test_twiml_is_valid_xml(self):
        """TwiML must be valid XML."""
        from app.services.ivr_service import IVRService
        svc = IVRService()
        twiml = svc._build_voice_twiml("LN_TEST", 50000.0)

        # Should not raise
        root = ElementTree.fromstring(twiml)
        assert root.tag == "Response"

    def test_twiml_has_preamble(self):
        """TwiML should start with a greeting before Gather."""
        from app.services.ivr_service import IVRService
        svc = IVRService()
        twiml = svc._build_voice_twiml("LN_TEST", 50000.0)

        root = ElementTree.fromstring(twiml)
        # First child should be a Say (preamble), not Gather
        first_child = list(root)[0]
        assert first_child.tag == "Say"
        assert "नमस्ते" in first_child.text

    def test_twiml_gather_has_single_digit(self):
        """Gather should collect exactly 1 digit."""
        from app.services.ivr_service import IVRService
        svc = IVRService()
        twiml = svc._build_voice_twiml("LN_TEST", 50000.0)

        root = ElementTree.fromstring(twiml)
        gather = root.find("Gather")
        assert gather is not None
        assert gather.get("numDigits") == "1"

    def test_twiml_three_gather_attempts(self):
        """TwiML should have exactly 3 Gather elements for retry."""
        from app.services.ivr_service import IVRService
        svc = IVRService()
        twiml = svc._build_voice_twiml("LN_TEST", 50000.0)

        root = ElementTree.fromstring(twiml)
        gathers = root.findall("Gather")
        assert len(gathers) == 3, f"Expected 3 Gather elements for retry, got {len(gathers)}"


class TestIVRTimeout:
    """Tests for the IVR timeout checking logic."""

    def test_within_window(self):
        """Loan started 10 seconds ago should be within window."""
        from app.services.ivr_service import IVRService

        class FakeLoan:
            ivr_window_started_at = datetime.now(timezone.utc) - timedelta(seconds=10)
            ivr_status = "pending"

        svc = IVRService()
        assert svc.is_within_window(FakeLoan()) is True

    def test_outside_window(self):
        """Loan started 120 seconds ago should be outside window."""
        from app.services.ivr_service import IVRService

        class FakeLoan:
            ivr_window_started_at = datetime.now(timezone.utc) - timedelta(seconds=120)
            ivr_status = "pending"

        svc = IVRService()
        assert svc.is_within_window(FakeLoan()) is False

    def test_no_window_started(self):
        """Loan with no window start should return False."""
        from app.services.ivr_service import IVRService

        class FakeLoan:
            ivr_window_started_at = None
            ivr_status = "pending"

        svc = IVRService()
        assert svc.is_within_window(FakeLoan()) is False

    def test_edge_of_window(self):
        """Loan at exactly 59 seconds should still be within window."""
        from app.services.ivr_service import IVRService

        class FakeLoan:
            ivr_window_started_at = datetime.now(timezone.utc) - timedelta(seconds=59)
            ivr_status = "pending"

        svc = IVRService()
        assert svc.is_within_window(FakeLoan()) is True

    def test_just_past_window(self):
        """Loan at exactly 61 seconds should be outside window."""
        from app.services.ivr_service import IVRService

        class FakeLoan:
            ivr_window_started_at = datetime.now(timezone.utc) - timedelta(seconds=61)
            ivr_status = "pending"

        svc = IVRService()
        assert svc.is_within_window(FakeLoan()) is False
