"""
CBS (Core Banking System) Validation Service.
Simulates Finacle/BaNCS middleware contract for loan eligibility.
Runs entirely in-process — same database, same Python runtime, zero network calls.
"""

import asyncio
import os
import uuid
from datetime import datetime, timezone
from typing import Dict, Any

from sqlalchemy.orm import Session

from app.models.loan import Loan
from dotenv import load_dotenv

load_dotenv()


CBS_MOCK_DELAY_MS = int(os.getenv("CBS_MOCK_DELAY_MS", "180"))


class CBSService:
    """Mock CBS validation that checks farmer loan eligibility using Finacle-style fields."""

    async def validate(self, db: Session, loan_id: str) -> Dict[str, Any]:
        """
        Validate loan eligibility against mock CBS.
        Returns Finacle-style response with LOAN_AC_NO, CUSTOMER_ID, etc.
        """
        loan = db.query(Loan).filter(Loan.loan_id == loan_id).first()
        if not loan:
            raise ValueError(f"Loan {loan_id} not found")

        # Simulate CBS network latency
        await asyncio.sleep(CBS_MOCK_DELAY_MS / 1000.0)

        # Check for existing active loans by same farmer
        existing_loans = (
            db.query(Loan)
            .filter(
                Loan.farmer_id == loan.farmer_id,
                Loan.loan_id != loan_id,
                Loan.status.in_(["executed", "anchored", "ready_for_execution"]),
            )
            .all()
        )

        # Check for any amount mismatch flags (declaration fraud indicators)
        has_mismatch = any(
            l.amount_difference_reason is not None for l in existing_loans
        )

        total_outstanding = sum(l.amount for l in existing_loans)

        # Determine NPA flag
        npa_flag = "Y" if has_mismatch else "N"

        # Eligibility logic
        if has_mismatch:
            eligibility = "WARNING"
            reason = "Previous loan has amount mismatch flag"
        elif total_outstanding > 2000000:
            eligibility = "WARNING"
            reason = f"Total outstanding ₹{total_outstanding:,.0f} exceeds ₹20,00,000 threshold"
        else:
            eligibility = "ELIGIBLE"
            reason = "All CBS checks passed"

        cbs_ref_id = f"CBS{uuid.uuid4().hex[:12].upper()}"

        return {
            "LOAN_AC_NO": loan_id,
            "CUSTOMER_ID": loan.farmer_id,
            "CUSTOMER_NAME": loan.farmer_name,
            "NPA_FLAG": npa_flag,
            "OUTSTANDING_AMT": total_outstanding,
            "REQUESTED_AMT": loan.amount,
            "ELIGIBILITY_STATUS": eligibility,
            "ELIGIBILITY_REASON": reason,
            "CBS_REF_ID": cbs_ref_id,
            "EXISTING_LOANS_COUNT": len(existing_loans),
            "VALIDATED_AT": datetime.now(timezone.utc).isoformat(),
        }
