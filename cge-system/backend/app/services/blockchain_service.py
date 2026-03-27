"""
Blockchain service for the CGE system.
Database-backed append-only hash chain (§3.5).
Primary anchor mechanism uses the blockchain_anchors SQLite table.
simple_blockchain.py is retained as the PoW prototype but no longer called.
"""

import json
import hashlib
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.blockchain import BlockchainAnchor

# Genesis constant
GENESIS_HASH = "0" * 64


class BlockchainService:
    """Database-backed append-only hash chain for consent anchoring."""

    def anchor_consent(
        self,
        db: Session,
        loan_id: str,
        final_consent_token: dict,
    ) -> BlockchainAnchor:
        """
        Hash the final consent token and anchor on the DB-backed chain.
        Computes block_hash = SHA256(prev_hash + consent_hash + anchored_at).
        """
        # Compute consent hash
        token_str = json.dumps(
            final_consent_token, sort_keys=True, separators=(",", ":")
        )
        consent_hash = hashlib.sha256(token_str.encode("utf-8")).hexdigest()

        # Get the most recent block for chain linking
        last_anchor = (
            db.query(BlockchainAnchor)
            .order_by(BlockchainAnchor.block_number.desc())
            .first()
        )
        prev_hash = last_anchor.transaction_hash if last_anchor else GENESIS_HASH
        block_number = (last_anchor.block_number + 1) if last_anchor else 1
        anchored_at = datetime.now(timezone.utc)

        # Compute block hash (§3.5)
        block_hash = hashlib.sha256(
            (prev_hash + consent_hash + anchored_at.isoformat()).encode("utf-8")
        ).hexdigest()

        block_data = {
            "block_number": block_number,
            "hash": block_hash,
            "prev_hash": prev_hash,
            "consent_hash": consent_hash,
            "loan_id": loan_id,
            "event": "consent_anchored",
            "timestamp": anchored_at.isoformat(),
        }

        # Create DB record — never UPDATE or DELETE
        anchor = BlockchainAnchor(
            loan_id=loan_id,
            consent_hash=consent_hash,
            block_number=block_number,
            transaction_hash=block_hash,
            anchored_at=anchored_at,
            blockchain_response=json.dumps(block_data),
        )
        db.add(anchor)
        db.commit()
        db.refresh(anchor)
        return anchor

    def get_anchor(self, db: Session, loan_id: str) -> Optional[BlockchainAnchor]:
        """Retrieve the blockchain anchor for a loan."""
        return (
            db.query(BlockchainAnchor)
            .filter(BlockchainAnchor.loan_id == loan_id)
            .first()
        )

    def verify_loan_anchor(self, db: Session, loan_id: str) -> Dict[str, Any]:
        """
        Verify a specific loan's blockchain anchor (§3.5).
        Recomputes block_hash from stored consent_hash and previous block's hash.
        """
        anchor = self.get_anchor(db, loan_id)
        if not anchor:
            return {
                "verified": False,
                "error": f"No blockchain anchor found for loan {loan_id}",
            }

        # Get the previous block
        if anchor.block_number > 1:
            prev_anchor = (
                db.query(BlockchainAnchor)
                .filter(BlockchainAnchor.block_number == anchor.block_number - 1)
                .first()
            )
            prev_hash = prev_anchor.transaction_hash if prev_anchor else GENESIS_HASH
        else:
            prev_hash = GENESIS_HASH

        # Reconstruct the original ISO timestamp used during hashing.
        # SQLite DateTime strips timezone info, but the hash was computed with
        # a UTC-aware datetime (e.g. "2026-03-25T17:18:41.785212+00:00").
        # Re-attach UTC timezone to get the same string.
        anchored_at = anchor.anchored_at
        if anchored_at and anchored_at.tzinfo is None:
            anchored_at = anchored_at.replace(tzinfo=timezone.utc)
        ts_str = anchored_at.isoformat() if anchored_at else ""

        # Recompute block hash
        recomputed = hashlib.sha256(
            (prev_hash + anchor.consent_hash + ts_str).encode("utf-8")
        ).hexdigest()

        verified = recomputed == anchor.transaction_hash

        return {
            "verified": verified,
            "loan_id": loan_id,
            "block_number": anchor.block_number,
            "transaction_hash": anchor.transaction_hash,
            "consent_hash": anchor.consent_hash,
            "anchored_at": anchor.anchored_at.isoformat() if anchor.anchored_at else None,
            "tamper_detected": not verified,
        }

    def verify_full_chain(self, db: Session) -> Dict[str, Any]:
        """
        Verify the entire chain from block 1 (§3.5).
        Recomputes each block's hash and checks against stored transaction_hash.
        """
        anchors = (
            db.query(BlockchainAnchor)
            .order_by(BlockchainAnchor.block_number.asc())
            .all()
        )

        if not anchors:
            return {
                "chain_valid": True,
                "total_blocks": 0,
                "verified_at": datetime.now(timezone.utc).isoformat(),
            }

        prev_hash = GENESIS_HASH
        for anchor in anchors:
            # Re-attach UTC timezone (SQLite strips it)
            anchored_at = anchor.anchored_at
            if anchored_at and anchored_at.tzinfo is None:
                anchored_at = anchored_at.replace(tzinfo=timezone.utc)
            ts_str = anchored_at.isoformat() if anchored_at else ""

            recomputed = hashlib.sha256(
                (prev_hash + anchor.consent_hash + ts_str).encode("utf-8")
            ).hexdigest()

            if recomputed != anchor.transaction_hash:
                return {
                    "chain_valid": False,
                    "broken_at_block": anchor.block_number,
                    "total_blocks": len(anchors),
                    "details": f"Hash mismatch at block {anchor.block_number}",
                    "verified_at": datetime.now(timezone.utc).isoformat(),
                }
            prev_hash = anchor.transaction_hash

        return {
            "chain_valid": True,
            "total_blocks": len(anchors),
            "last_block_hash": anchors[-1].transaction_hash,
            "verified_at": datetime.now(timezone.utc).isoformat(),
        }

    # Legacy compatibility methods
    def verify_chain_integrity(self) -> Dict[str, Any]:
        """Legacy method — creates its own session for backward compatibility."""
        from app.db.database import SessionLocal
        db = SessionLocal()
        try:
            result = self.verify_full_chain(db)
            return {
                "is_valid": result.get("chain_valid", True),
                "chain_length": result.get("total_blocks", 0),
                "last_block_hash": result.get("last_block_hash"),
                "verified_at": result.get("verified_at"),
            }
        finally:
            db.close()

    def get_full_chain(self) -> List[Dict]:
        """Return the full chain from the database."""
        from app.db.database import SessionLocal
        db = SessionLocal()
        try:
            anchors = (
                db.query(BlockchainAnchor)
                .order_by(BlockchainAnchor.block_number.asc())
                .all()
            )
            return [
                json.loads(a.blockchain_response) if a.blockchain_response else {
                    "block_number": a.block_number,
                    "hash": a.transaction_hash,
                    "consent_hash": a.consent_hash,
                }
                for a in anchors
            ]
        finally:
            db.close()

    def get_block(self, block_number: int) -> Dict:
        """Get a specific block by index."""
        from app.db.database import SessionLocal
        db = SessionLocal()
        try:
            anchor = (
                db.query(BlockchainAnchor)
                .filter(BlockchainAnchor.block_number == block_number)
                .first()
            )
            if not anchor:
                return {}
            if anchor.blockchain_response:
                return json.loads(anchor.blockchain_response)
            return {
                "block_number": anchor.block_number,
                "hash": anchor.transaction_hash,
                "consent_hash": anchor.consent_hash,
                "data": {"consent_hash": anchor.consent_hash},
            }
        finally:
            db.close()
