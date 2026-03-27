"""
KioskPresenceRecord model — captures physical presence evidence at the kiosk.
Includes GPS, photo hash, Aadhaar verification, and device fingerprint.
"""

from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Text, ForeignKey
from datetime import datetime, timezone

from app.db.database import Base


class KioskPresenceRecord(Base):
    __tablename__ = "kiosk_presence_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    loan_id = Column(String(50), ForeignKey("loans.loan_id"), nullable=False, index=True)
    gps_latitude = Column(Float, nullable=True)
    gps_longitude = Column(Float, nullable=True)
    gps_captured_at = Column(DateTime, nullable=True)
    photo_hash = Column(String(64), nullable=True)  # SHA-256 of captured photo
    photo_encrypted_storage_path = Column(String(500), nullable=True)
    aadhaar_last_four = Column(String(4), nullable=True)
    aadhaar_hash = Column(String(64), nullable=True)  # SHA-256 of full Aadhaar number
    aadhaar_verified_name = Column(String(255), nullable=True)
    aadhaar_otp_verified = Column(Boolean, default=False)
    aadhaar_verified_at = Column(DateTime, nullable=True)
    device_fingerprint = Column(Text, nullable=True)  # JSON (legacy)
    device_fingerprint_hash = Column(String(64), nullable=True)  # SHA-256 of device fingerprint
    terms_accepted_at = Column(DateTime, nullable=True)
    terms_scroll_completed = Column(Boolean, default=False)
    face_detected_client_side = Column(Boolean, default=False)
    liveness_check_suspicious = Column(Boolean, default=False)
    photo_captured_at = Column(DateTime, nullable=True)  # Server-authoritative timestamp
    assisting_employee_name = Column(String(255), nullable=True)
    assisting_employee_id = Column(String(100), nullable=True)

    # ── Active Liveness Verification (Layered Model) ──
    active_liveness_passed = Column(Boolean, default=False)      # Overall active liveness result
    liveness_blink_detected = Column(Boolean, default=False)     # Blink challenge passed
    liveness_head_turn_detected = Column(Boolean, default=False) # Head turn challenge passed
    liveness_smile_detected = Column(Boolean, default=False)     # Smile challenge passed
    liveness_challenges_json = Column(Text, nullable=True)       # Full challenge metadata JSON
    face_count_client = Column(Integer, nullable=True)           # Faces detected client-side
    face_centered = Column(Boolean, default=False)               # Face was centered when captured
    auto_captured = Column(Boolean, default=False)               # Photo was auto-captured (not manual)

    # ── Aadhaar QR Scan + Face Match (Step 3 & Step 5) ──
    aadhaar_qr_photo_encrypted_path = Column(String(500), nullable=True)  # Encrypted QR photo storage path
    aadhaar_qr_scanned_at = Column(DateTime, nullable=True)               # Timestamp of successful QR scan
    face_match_score = Column(Float, nullable=True)                       # Similarity score from face comparison
    face_match_passed = Column(Boolean, nullable=True)                    # Whether face match passed threshold
    face_match_attempts = Column(Integer, default=0)                      # Number of match attempts

    def __repr__(self):
        return f"<KioskPresenceRecord(loan_id={self.loan_id}, aadhaar_verified={self.aadhaar_otp_verified})>"
