"""
LoanDocument model — stores document hashes, OCR results, and farmer confirmations.
Document hash is computed immediately on receipt and is immutable thereafter.
"""

from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Text, ForeignKey
from datetime import datetime, timezone

from app.db.database import Base


class LoanDocument(Base):
    __tablename__ = "loan_documents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    loan_id = Column(String(50), ForeignKey("loans.loan_id"), unique=True, nullable=False)
    document_hash = Column(String(64), nullable=False)  # SHA-256 of raw uploaded file bytes
    signature_region_hash = Column(String(64), nullable=True)  # SHA-256 of cropped signature region
    encrypted_document_path = Column(String(500), nullable=True)
    ocr_extracted_amount = Column(Float, nullable=True)
    ocr_extracted_purpose = Column(Text, nullable=True)
    ocr_extracted_farmer_name = Column(String(255), nullable=True)
    ocr_confidence_score = Column(Float, nullable=True)  # 0 to 1
    farmer_confirmed_amount = Column(Float, nullable=True)
    farmer_confirmed_purpose = Column(Text, nullable=True)
    ocr_confirmation_attempts = Column(Integer, default=0)
    ocr_confirmed_at = Column(DateTime, nullable=True)
    document_uploaded_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    employee_assistance_used = Column(Boolean, default=False)
    assisting_employee_id = Column(String(100), nullable=True)

    # ── Structured OCR extraction fields ──
    ocr_extracted_account_number = Column(String(20), nullable=True)
    ocr_extracted_ifsc = Column(String(11), nullable=True)
    ocr_extracted_phone = Column(String(15), nullable=True)
    ocr_extracted_aadhaar_masked = Column(String(20), nullable=True)   # XXXX-XXXX-1234
    ocr_extracted_annual_income = Column(Float, nullable=True)
    ocr_extracted_land_ownership = Column(Text, nullable=True)
    ocr_extracted_loan_reason = Column(Text, nullable=True)
    ocr_structured_fields_encrypted = Column(Text, nullable=True)      # Full encrypted JSON
    ocr_field_confidences_json = Column(Text, nullable=True)           # Per-field confidence JSON
    ocr_needs_review_fields = Column(Text, nullable=True)              # Comma-separated low-confidence fields
    ocr_engine_used = Column(String(50), nullable=True)                # paddleocr / tesseract
    form_photo_hash = Column(String(64), nullable=True)                # SHA-256 of cropped photo box
    form_photo_encrypted_path = Column(String(500), nullable=True)     # Fernet-encrypted form photo

    # ── Farmer-confirmed structured fields ──
    farmer_confirmed_account_number = Column(String(20), nullable=True)
    farmer_confirmed_ifsc = Column(String(11), nullable=True)
    farmer_confirmed_phone = Column(String(15), nullable=True)
    farmer_confirmed_annual_income = Column(Float, nullable=True)
    farmer_confirmed_land_ownership = Column(Text, nullable=True)
    farmer_confirmed_loan_reason = Column(Text, nullable=True)

    # ── OCR pipeline tracking ──
    ocr_source = Column(String(50), nullable=True)           # google_vision / paddleocr / tesseract / manual
    ocr_fallback_used = Column(Boolean, default=False)       # True if primary (Google Vision) failed

    def __repr__(self):
        return f"<LoanDocument(loan_id={self.loan_id}, hash={self.document_hash[:16]}...)>"
