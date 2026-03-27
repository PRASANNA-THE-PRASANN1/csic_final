"""
SMS Service – Mock implementation for sending SMS notifications.
In production, this would integrate with MSG91/Twilio/AWS SNS.
For the demo, it logs messages to console.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class SMSService:
    """
    Mock SMS gateway for sending notifications to farmers and bank staff.
    """

    def __init__(self):
        self.is_mock = True
        self.sent_messages = []  # Keep track for demo/testing

    def send_sms(self, mobile: str, message: str) -> dict:
        """
        Send an SMS message (mock – logs to console).

        Returns:
            {"success": True, "message_id": str, "mock": True}
        """
        import uuid
        message_id = f"MSG_{uuid.uuid4().hex[:8].upper()}"

        log_entry = {
            "message_id": message_id,
            "mobile": mobile,
            "message": message,
            "mock": True,
        }
        self.sent_messages.append(log_entry)

        logger.info(f"📱 [MOCK SMS] To: {mobile}")
        logger.info(f"   Message: {message}")
        print(f"📱 [MOCK SMS] To: {mobile} | {message}")

        return {"success": True, "message_id": message_id, "mock": True}

    def send_declaration_confirmation(self, mobile: str, declaration_id: str, amount: float) -> dict:
        """Send confirmation after farmer submits a loan declaration."""
        message = (
            f"[CGE Bank] Your loan declaration {declaration_id} for ₹{amount:,.2f} "
            f"has been recorded. Share this ID with the bank clerk when applying."
        )
        return self.send_sms(mobile, message)

    def send_loan_creation_confirmation(
        self, mobile: str, loan_id: str, amount: float, declared_amount: Optional[float] = None
    ) -> dict:
        """Send confirmation after clerk creates a loan application."""
        message = (
            f"[CGE Bank] Loan application {loan_id} for ₹{amount:,.2f} has been created. "
        )
        if declared_amount and abs(amount - declared_amount) > 0.01:
            message += (
                f" Note: Your declared amount was ₹{declared_amount:,.2f}. "
                f"Difference: ₹{abs(amount - declared_amount):,.2f}."
            )
        else:
            message += "The amount matches your declaration. "
        return self.send_sms(mobile, message)

    def send_consent_confirmation(self, mobile: str, loan_id: str) -> dict:
        """Send confirmation after farmer provides consent."""
        message = (
            f"[CGE Bank] Your consent for loan {loan_id} has been recorded "
            f"with cryptographic proof. Your rights are protected."
        )
        return self.send_sms(mobile, message)

    def send_disbursement_confirmation(
        self, mobile: str, loan_id: str, account_number: str
    ) -> dict:
        """Send confirmation after disbursement account is verified."""
        masked_account = f"****{account_number[-4:]}" if len(account_number) >= 4 else "****"
        message = (
            f"[CGE Bank] Disbursement for loan {loan_id} will be sent to "
            f"account {masked_account}. If this is not your account, "
            f"call 1800-XXX-XXXX immediately."
        )
        return self.send_sms(mobile, message)
