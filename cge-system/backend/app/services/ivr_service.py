"""
IVR Service — Twilio voice call + SMS fallback for consent confirmation.
Implements a strict 60-second window after OTP verification.

Voice TwiML uses Amazon Polly "Aditi" (Hindi) with a 3-attempt Gather loop
so the farmer gets multiple chances to press 1 (confirm) or 2 (reject).
"""

import os
import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER", "")

IVR_WINDOW_SECONDS = 60


class IVRService:
    """Handles IVR voice calls and SMS fallback for loan consent confirmation."""

    def __init__(self):
        self._client = None

    @property
    def client(self):
        """Lazy-initialize Twilio client."""
        if self._client is None:
            try:
                from twilio.rest import Client
                self._client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
                logger.info("Twilio client initialized successfully")
            except Exception as e:
                logger.warning(f"Twilio client init failed: {e}. IVR calls will be simulated.")
                self._client = None
        return self._client

    @staticmethod
    def _get_webhook_base_url() -> str:
        """Read VOICE_WEBHOOK_BASE_URL at call time (not module import time).
        Raises ValueError if unconfigured so calls don't silently use a dead URL."""
        url = os.getenv("VOICE_WEBHOOK_BASE_URL", "")
        if not url or url == "https://placeholder.ngrok.io":
            raise ValueError(
                "VOICE_WEBHOOK_BASE_URL is not configured. "
                "Set it to your ngrok/Railway URL before placing IVR calls."
            )
        return url.rstrip("/")

    def _build_voice_twiml(self, loan_id: str, loan_amount: float) -> str:
        """Build TwiML XML string for the IVR consent call.

        Structure:
        1. Preamble greeting
        2. Gather loop (up to 3 attempts) asking farmer to press 1 or 2
        3. Final "no input" message if all attempts exhausted

        Uses Polly.Aditi voice for native Hindi TTS.
        """
        base_url = self._get_webhook_base_url()
        webhook_url = f"{base_url}/api/ivr/webhook?loan_id={loan_id}"
        amount_display = f"{int(loan_amount)}"

        # Hindi messages
        preamble = (
            "नमस्ते। यह कॉल आपके बैंक ऋण आवेदन की पुष्टि के लिए है।"
        )
        gather_prompt = (
            f"आपने {amount_display} रुपये का ऋण आवेदन किया है। "
            f"पुष्टि करने के लिए 1 दबाएँ। "
            f"अस्वीकार करने के लिए 2 दबाएँ।"
        )
        retry_prompt = (
            "कोई इनपुट नहीं मिला। कृपया दोबारा प्रयास करें। "
            f"पुष्टि के लिए 1 दबाएँ, अस्वीकार के लिए 2 दबाएँ।"
        )
        final_no_input = (
            "कोई इनपुट नहीं मिला। आपका आवेदन रद्द हो सकता है। धन्यवाद।"
        )

        voice = 'Polly.Aditi'

        # Build TwiML XML manually for full control
        # Attempt 1: Preamble + first Gather
        xml_parts = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<Response>',
            f'<Say voice="{voice}" language="hi-IN">{preamble}</Say>',
            f'<Gather numDigits="1" action="{webhook_url}" method="POST" timeout="10">',
            f'<Say voice="{voice}" language="hi-IN">{gather_prompt}</Say>',
            '</Gather>',
            # Attempt 2: retry
            f'<Say voice="{voice}" language="hi-IN">{retry_prompt}</Say>',
            f'<Gather numDigits="1" action="{webhook_url}" method="POST" timeout="10">',
            f'<Say voice="{voice}" language="hi-IN">{gather_prompt}</Say>',
            '</Gather>',
            # Attempt 3: final retry
            f'<Say voice="{voice}" language="hi-IN">{retry_prompt}</Say>',
            f'<Gather numDigits="1" action="{webhook_url}" method="POST" timeout="10">',
            f'<Say voice="{voice}" language="hi-IN">{gather_prompt}</Say>',
            '</Gather>',
            # No input after 3 attempts
            f'<Say voice="{voice}" language="hi-IN">{final_no_input}</Say>',
            '</Response>',
        ]

        return ''.join(xml_parts)

    def trigger_ivr_call(self, db: Session, loan_id: str, farmer_phone: str, loan_amount: float):
        """
        Place a Twilio voice call to the farmer for consent confirmation.
        Sets ivr_status = 'pending', increments ivr_attempts, records ivr_window_started_at.
        """
        from app.models.loan import Loan

        loan = db.query(Loan).filter(Loan.loan_id == loan_id).first()
        if not loan:
            raise ValueError(f"Loan {loan_id} not found")

        # Set window start time on first call
        now = datetime.now(timezone.utc)
        if not loan.ivr_window_started_at:
            loan.ivr_window_started_at = now

        loan.ivr_status = "pending"
        loan.ivr_attempts = (loan.ivr_attempts or 0) + 1
        db.commit()

        # Build TwiML (reads VOICE_WEBHOOK_BASE_URL dynamically)
        base_url = self._get_webhook_base_url()
        twiml_xml = self._build_voice_twiml(loan_id, loan_amount)
        webhook_url = f"{base_url}/api/ivr/webhook?loan_id={loan_id}"

        try:
            if self.client:
                # Place the call using inline TwiML
                call = self.client.calls.create(
                    to=farmer_phone,
                    from_=TWILIO_PHONE_NUMBER,
                    twiml=twiml_xml,
                    status_callback=f"{base_url}/api/ivr/call-status?loan_id={loan_id}",
                    status_callback_event=["completed", "busy", "no-answer", "failed"],
                    status_callback_method="POST",
                )
                logger.info(f"📞 IVR call placed: loan={loan_id}, call_sid={call.sid}")
                print(f"📞 [IVR] Call placed to {farmer_phone} for loan {loan_id} (SID: {call.sid})")
                print(f"   TwiML webhook URL: {webhook_url}")
                return {"success": True, "call_sid": call.sid}
            else:
                # Simulation mode — log what would happen
                logger.info(f"📞 [SIMULATED IVR] Call to {farmer_phone} for loan {loan_id}")
                print(f"📞 [SIMULATED IVR] Call to {farmer_phone} | Amount: ₹{int(loan_amount)} | Loan: {loan_id}")
                print(f"   Webhook: {webhook_url}")
                print(f"   To manually simulate confirmation, POST to:")
                print(f"   curl -X POST \"http://localhost:8000/api/ivr/webhook?loan_id={loan_id}\" "
                      f"-d \"Digits=1\" -H \"Content-Type: application/x-www-form-urlencoded\"")
                return {"success": True, "call_sid": "SIM_" + loan_id, "simulated": True}
        except Exception as e:
            logger.error(f"IVR call failed for loan {loan_id}: {e}")
            print(f"❌ [IVR] Call failed for {loan_id}: {e}")
            # Call failed — trigger SMS fallback immediately
            self.trigger_sms_fallback(db, loan_id, farmer_phone, loan_amount)
            return {"success": False, "error": str(e), "sms_fallback_triggered": True}

    def trigger_sms_fallback(self, db: Session, loan_id: str, farmer_phone: str, loan_amount: float):
        """
        Send SMS fallback when IVR call fails.
        Uses Twilio SMS. Sets consent_final_method = 'sms'.
        """
        from app.models.loan import Loan

        loan = db.query(Loan).filter(Loan.loan_id == loan_id).first()
        if not loan:
            raise ValueError(f"Loan {loan_id} not found")

        loan.consent_final_method = "sms"
        db.commit()

        message_body = (
            f"Reply YES to confirm your loan of Rs.{int(loan_amount)}. "
            f"Reply NO to reject. Loan ID: {loan_id}"
        )

        try:
            if self.client:
                sms_webhook_url = f"{os.getenv('VOICE_WEBHOOK_BASE_URL', '')}/api/ivr/sms-webhook?loan_id={loan_id}"
                msg = self.client.messages.create(
                    to=farmer_phone,
                    from_=TWILIO_PHONE_NUMBER,
                    body=message_body,
                    status_callback=sms_webhook_url,
                )
                logger.info(f"📱 SMS fallback sent: loan={loan_id}, sid={msg.sid}")
                print(f"📱 [SMS FALLBACK] Sent to {farmer_phone} for loan {loan_id} (SID: {msg.sid})")
            else:
                logger.info(f"📱 [SIMULATED SMS] To {farmer_phone}: {message_body}")
                print(f"📱 [SIMULATED SMS] To {farmer_phone} | {message_body}")
        except Exception as e:
            logger.error(f"SMS fallback failed for loan {loan_id}: {e}")
            print(f"❌ [SMS FALLBACK] Failed for {loan_id}: {e}")

    def check_ivr_timeout(self, db: Session, loan) -> bool:
        """
        Check if the 60-second IVR window has expired.
        If expired and status is still 'pending', reject the loan.
        Returns True if timed out.
        """
        if not loan.ivr_window_started_at:
            return False
        if loan.ivr_status not in ("pending", "failed"):
            return False

        window_start = loan.ivr_window_started_at
        if window_start.tzinfo is None:
            window_start = window_start.replace(tzinfo=timezone.utc)

        elapsed = (datetime.now(timezone.utc) - window_start).total_seconds()
        if elapsed >= IVR_WINDOW_SECONDS:
            loan.ivr_status = "timed_out"
            self.reject_loan(db, loan)
            logger.info(f"⏱ IVR timed out for loan {loan.loan_id} after {elapsed:.0f}s")
            print(f"⏱ [IVR TIMEOUT] Loan {loan.loan_id} rejected after {elapsed:.0f}s")
            return True
        return False

    def reject_loan(self, db: Session, loan):
        """Set loan to kiosk_rejected and expire the kiosk session."""
        from app.models.kiosk_session import KioskSession

        loan.status = "kiosk_rejected"
        loan.updated_at = datetime.now(timezone.utc)

        session = db.query(KioskSession).filter(KioskSession.loan_id == loan.loan_id).first()
        if session:
            session.session_status = "expired"

        db.commit()

    def is_within_window(self, loan) -> bool:
        """Check if the current time is within the 60-second IVR window."""
        if not loan.ivr_window_started_at:
            return False

        window_start = loan.ivr_window_started_at
        if window_start.tzinfo is None:
            window_start = window_start.replace(tzinfo=timezone.utc)

        elapsed = (datetime.now(timezone.utc) - window_start).total_seconds()
        return elapsed < IVR_WINDOW_SECONDS
