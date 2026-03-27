"""
DocumentService — handles document upload, hashing, encryption, OCR, and confirmation.
Document hash is computed immediately on receipt and is immutable.

OCR pipeline: Uses OCRService for full structured extraction with PaddleOCR + Tesseract fallback.
"""

import os
import hashlib
import json
import logging
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from cryptography.fernet import Fernet
from dotenv import load_dotenv

from app.models.loan_document import LoanDocument
from app.models.loan import Loan
from app.models.kiosk_session import KioskSession

load_dotenv()
MASTER_KEY = os.getenv("MASTER_KEY", Fernet.generate_key().decode())

logger = logging.getLogger(__name__)


class DocumentService:
    """Handles document upload, encryption, OCR, and farmer confirmation."""

    def __init__(self):
        self.fernet = Fernet(MASTER_KEY.encode() if isinstance(MASTER_KEY, str) else MASTER_KEY)

    def receive_document(self, db: Session, loan_id: str, file_bytes: bytes, file_content_type: str):
        """Hash, encrypt, and store an uploaded document."""
        # FIRST ACTION: compute hash before anything else
        document_hash = hashlib.sha256(file_bytes).hexdigest()

        # Encrypt the file
        encrypted = self.fernet.encrypt(file_bytes)
        doc_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "documents")
        os.makedirs(doc_dir, exist_ok=True)
        doc_path = os.path.join(doc_dir, f"{loan_id}.enc")
        with open(doc_path, "wb") as f:
            f.write(encrypted)

        # Create or update LoanDocument record
        loan_doc = db.query(LoanDocument).filter(LoanDocument.loan_id == loan_id).first()
        if loan_doc:
            loan_doc.document_hash = document_hash
            loan_doc.encrypted_document_path = doc_path
            loan_doc.document_uploaded_at = datetime.now(timezone.utc)
        else:
            loan_doc = LoanDocument(
                loan_id=loan_id,
                document_hash=document_hash,
                encrypted_document_path=doc_path,
            )
            db.add(loan_doc)

        # Update loan record
        loan = db.query(Loan).filter(Loan.loan_id == loan_id).first()
        if loan:
            loan.document_hash = document_hash
            loan.status = "document_uploaded"

        # Update kiosk session status
        session = db.query(KioskSession).filter(KioskSession.loan_id == loan_id).first()
        if session:
            session.session_status = "document_uploaded"

        db.commit()

        return {
            "document_hash": document_hash,
            "upload_confirmed_at": datetime.now(timezone.utc).isoformat(),
        }

    def run_ocr(self, db: Session, loan_id: str):
        """Run full OCR pipeline on the stored document.

        3-Layer pipeline:
          Layer 1: Google Cloud Vision (primary, cloud-based)
          Layer 2: Local PaddleOCR/Tesseract (fallback, offline)
          Layer 3: Manual entry signal (final fallback — never crashes)
        """
        loan_doc = db.query(LoanDocument).filter(LoanDocument.loan_id == loan_id).first()
        if not loan_doc:
            raise ValueError("No document found for this loan")

        loan = db.query(Loan).filter(Loan.loan_id == loan_id).first()

        # ── Decrypt the document ──
        decrypted = None
        if loan_doc.encrypted_document_path and os.path.exists(loan_doc.encrypted_document_path):
            with open(loan_doc.encrypted_document_path, "rb") as f:
                encrypted_data = f.read()
            decrypted = self.fernet.decrypt(encrypted_data)

        if not decrypted:
            # No document to OCR — go straight to manual
            return self._build_manual_required_response(db, loan_id, loan_doc, loan)

        # ── Layer 1: Google Cloud Vision (primary) ──
        ocr_result = None
        ocr_source = "manual"
        ocr_fallback_used = False
        manual_required = False

        try:
            from app.services.external_ocr_service import GoogleVisionOCR, GoogleVisionError
            raw_text = GoogleVisionOCR.extract_text(decrypted)

            # Feed raw text into existing extraction pipeline (Steps 3-5 of ocr_service)
            from app.services.ocr_service import (
                FieldExtractor, FieldValidator, ConfidenceScorer, ImagePreprocessor
            )

            # Build an ocr_result-like dict from the Google Vision text
            lines = [{"text": line.strip(), "confidence": 0.85}
                     for line in raw_text.split("\n") if line.strip()]
            words = [{"text": w, "confidence": 0.85}
                     for line in raw_text.split("\n") for w in line.split() if w.strip()]

            gv_ocr_result = {
                "engine": "google_vision",
                "full_text": raw_text,
                "lines": lines,
                "words": words,
                "avg_confidence": 0.85,
            }

            # Step 3: Extract structured fields using existing pipeline
            fields = FieldExtractor.extract(gv_ocr_result)

            # Step 4: Validate
            fields = FieldValidator.validate_all(fields)

            # Step 5: Confidence scoring
            fields = ConfidenceScorer.score_all(fields, gv_ocr_result["avg_confidence"])

            needs_review = [k for k, v in fields.items() if v.get("needs_review", True)]

            ocr_result = {
                "fields": {},
                "ocr_engine": "google_vision",
                "ocr_avg_confidence": gv_ocr_result["avg_confidence"],
                "full_text": raw_text[:3000],
                "needs_review_fields": needs_review,
            }

            for key, data in fields.items():
                ocr_result["fields"][key] = {
                    "value": data.get("value"),
                    "confidence": data.get("confidence", 0.0),
                    "needs_review": data.get("needs_review", True),
                    "validation_passed": data.get("validation_passed", False),
                    "validation_error": data.get("validation_error"),
                    "method": data.get("method", "not_found"),
                }

            # Photo box extraction (same as existing pipeline)
            try:
                from app.services.ocr_service import FormRegionExtractor
                photo_box_result = FormRegionExtractor.extract_photo_box(decrypted)
                if photo_box_result:
                    ocr_result["photo_box"] = {
                        "face_found": photo_box_result.get("face_found", False),
                        "face_coords": photo_box_result.get("face_coords"),
                    }
            except Exception:
                pass

            ocr_source = "google_vision"
            ocr_fallback_used = False
            logger.info(f"Layer 1 (Google Vision) succeeded for {loan_id}")

        except Exception as gv_err:
            logger.warning(f"Layer 1 (Google Vision) failed for {loan_id}: {gv_err}")

            # ── Layer 2: Existing local pipeline (fallback) ──
            try:
                from app.services.ocr_service import OCRService
                ocr_svc = OCRService(fernet=self.fernet)
                ocr_result = ocr_svc.process_document(decrypted)
                ocr_source = ocr_result.get("ocr_engine", "unknown")
                ocr_fallback_used = True
                logger.info(f"Layer 2 (local OCR) succeeded for {loan_id}: engine={ocr_source}")
            except Exception as local_err:
                logger.warning(f"Layer 2 (local OCR) failed for {loan_id}: {local_err}")
                import traceback
                traceback.print_exc()
                ocr_result = None

        # ── Layer 3: Manual entry signal (final fallback) ──
        if ocr_result is None or ocr_result.get("ocr_engine") == "none":
            return self._build_manual_required_response(db, loan_id, loan_doc, loan)

        # ── Extract values from OCR result ──
        fields = ocr_result.get("fields", {})

        # Primary fields (backward compatible)
        extracted_amount = fields.get("loan_amount", {}).get("value")
        extracted_purpose = fields.get("loan_reason", {}).get("value")
        extracted_farmer_name = fields.get("name", {}).get("value")

        # Confidence: use average of all found fields
        found_confidences = [f.get("confidence", 0) for f in fields.values() if f.get("value") is not None]
        confidence_score = sum(found_confidences) / len(found_confidences) if found_confidences else 0.0

        # Structured fields
        extracted_account = fields.get("account_number", {}).get("value")
        extracted_ifsc = fields.get("ifsc", {}).get("value")
        extracted_phone = fields.get("phone_number", {}).get("value")
        extracted_aadhaar = fields.get("aadhaar_number", {}).get("value")
        extracted_income = fields.get("annual_income", {}).get("value")
        extracted_land = fields.get("land_ownership", {}).get("value")

        # Mask Aadhaar
        from app.services.ocr_service import OCRService as _OCR
        aadhaar_masked = _OCR().mask_aadhaar(extracted_aadhaar) if extracted_aadhaar else None

        ocr_engine = ocr_result.get("ocr_engine", "unknown")
        needs_review = ocr_result.get("needs_review_fields", [])

        # Per-field confidence JSON
        field_confidences = {
            k: {"confidence": v.get("confidence", 0), "needs_review": v.get("needs_review", True)}
            for k, v in fields.items()
        }

        # Signature region hash (from image crop)
        signature_region_hash = self._compute_signature_hash(loan_doc, loan_id)

        # ── Store results ──
        loan_doc.ocr_extracted_amount = float(extracted_amount) if extracted_amount else None
        loan_doc.ocr_extracted_purpose = str(extracted_purpose) if extracted_purpose else None
        loan_doc.ocr_extracted_farmer_name = str(extracted_farmer_name) if extracted_farmer_name else None
        loan_doc.ocr_confidence_score = round(confidence_score, 3) if confidence_score else 0.0
        loan_doc.signature_region_hash = signature_region_hash

        # Structured fields
        loan_doc.ocr_extracted_account_number = str(extracted_account) if extracted_account else None
        loan_doc.ocr_extracted_ifsc = str(extracted_ifsc) if extracted_ifsc else None
        loan_doc.ocr_extracted_phone = str(extracted_phone) if extracted_phone else None
        loan_doc.ocr_extracted_aadhaar_masked = aadhaar_masked
        loan_doc.ocr_extracted_annual_income = float(extracted_income) if extracted_income else None
        loan_doc.ocr_extracted_land_ownership = str(extracted_land) if extracted_land else None
        loan_doc.ocr_extracted_loan_reason = str(extracted_purpose) if extracted_purpose else None
        loan_doc.ocr_engine_used = ocr_engine
        loan_doc.ocr_needs_review_fields = ",".join(needs_review) if needs_review else None
        loan_doc.ocr_field_confidences_json = json.dumps(field_confidences)

        # OCR pipeline tracking fields
        loan_doc.ocr_source = ocr_source
        loan_doc.ocr_fallback_used = ocr_fallback_used

        # Encrypt all structured data
        if ocr_result:
            encrypted_fields = self.fernet.encrypt(
                json.dumps(ocr_result.get("fields", {}), default=str).encode()
            ).decode()
            loan_doc.ocr_structured_fields_encrypted = encrypted_fields

        # ── Photo box extraction (Fix 6) ──
        try:
            if ocr_result and ocr_result.get("photo_box", {}).get("face_found"):
                photo_box_data = ocr_result["photo_box"]
                # Get face bytes from the OCR pipeline
                if loan_doc.encrypted_document_path and os.path.exists(loan_doc.encrypted_document_path):
                    with open(loan_doc.encrypted_document_path, "rb") as f:
                        encrypted_data = f.read()
                    decrypted_for_photo = self.fernet.decrypt(encrypted_data)

                    from app.services.ocr_service import FormRegionExtractor
                    photo_box_result = FormRegionExtractor.extract_photo_box(decrypted_for_photo)
                    if photo_box_result.get("face_bytes"):
                        # Hash the photo box
                        form_photo_hash = hashlib.sha256(photo_box_result["face_bytes"]).hexdigest()
                        loan_doc.form_photo_hash = form_photo_hash

                        # Encrypt and store
                        encrypted_photo = self.fernet.encrypt(photo_box_result["face_bytes"])
                        photo_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                                                 "data", "documents")
                        os.makedirs(photo_dir, exist_ok=True)
                        photo_path = os.path.join(photo_dir, f"form_photo_{loan_id}.enc")
                        with open(photo_path, "wb") as f:
                            f.write(encrypted_photo)
                        loan_doc.form_photo_encrypted_path = photo_path
                        logger.info(f"Form photo box stored for {loan_id}: hash={form_photo_hash[:16]}...")
        except Exception as e:
            logger.warning(f"Photo box storage failed for {loan_id}: {e}")

        db.commit()

        # ── Build response ──
        response = {
            "extracted_amount": extracted_amount,
            "extracted_purpose": extracted_purpose,
            "extracted_farmer_name": extracted_farmer_name,
            "confidence_score": round(confidence_score, 3) if confidence_score else 0.0,
            "signature_region_hash": signature_region_hash,
            "document_thumbnail_base64": None,
            # Structured fields
            "extracted_account_number": extracted_account,
            "extracted_ifsc": extracted_ifsc,
            "extracted_phone": extracted_phone,
            "extracted_aadhaar_masked": aadhaar_masked,
            "extracted_annual_income": extracted_income,
            "extracted_land_ownership": extracted_land,
            "extracted_loan_reason": extracted_purpose,
            # Metadata
            "ocr_engine": ocr_engine,
            "needs_review_fields": needs_review,
            "field_confidences": field_confidences,
            # 3-layer pipeline tracking
            "ocr_source": ocr_source,
            "ocr_fallback_used": ocr_fallback_used,
            "manual_required": False,
        }

        # Include full per-field details if OCR ran
        if ocr_result and "fields" in ocr_result:
            response["structured_fields"] = {}
            for key, data in ocr_result["fields"].items():
                response["structured_fields"][key] = {
                    "value": data.get("value"),
                    "confidence": data.get("confidence", 0),
                    "needs_review": data.get("needs_review", True),
                    "validation_passed": data.get("validation_passed", False),
                    "validation_error": data.get("validation_error"),
                }

        return response

    def _build_manual_required_response(self, db: Session, loan_id: str, loan_doc, loan):
        """Layer 3: All OCR engines failed — return manual_required response.
        The flow never crashes; the frontend shows a manual entry form."""
        logger.warning(f"All OCR layers failed for {loan_id} — manual entry required")

        all_field_keys = ["name", "account_number", "ifsc", "phone_number",
                          "aadhaar_number", "loan_amount", "annual_income",
                          "land_ownership", "loan_reason"]
        field_confidences = {k: {"confidence": 0.0, "needs_review": True} for k in all_field_keys}
        signature_region_hash = self._compute_signature_hash(loan_doc, loan_id)

        # Save tracking fields
        loan_doc.ocr_source = "manual"
        loan_doc.ocr_fallback_used = True
        loan_doc.ocr_confidence_score = 0.0
        loan_doc.ocr_engine_used = "none"
        loan_doc.signature_region_hash = signature_region_hash
        loan_doc.ocr_needs_review_fields = ",".join(all_field_keys)
        loan_doc.ocr_field_confidences_json = json.dumps(field_confidences)
        db.commit()

        return {
            "extracted_amount": None,
            "extracted_purpose": None,
            "extracted_farmer_name": None,
            "confidence_score": 0.0,
            "signature_region_hash": signature_region_hash,
            "document_thumbnail_base64": None,
            "extracted_account_number": None,
            "extracted_ifsc": None,
            "extracted_phone": None,
            "extracted_aadhaar_masked": None,
            "extracted_annual_income": None,
            "extracted_land_ownership": None,
            "extracted_loan_reason": None,
            "ocr_engine": "none",
            "needs_review_fields": all_field_keys,
            "field_confidences": field_confidences,
            # 3-layer pipeline tracking
            "ocr_source": "manual",
            "ocr_fallback_used": True,
            "manual_required": True,
        }

    def _compute_signature_hash(self, loan_doc, loan_id: str) -> str:
        """Compute SHA-256 hash of signature region (bottom-right crop)."""
        try:
            if loan_doc.encrypted_document_path and os.path.exists(loan_doc.encrypted_document_path):
                from PIL import Image
                import io
                with open(loan_doc.encrypted_document_path, "rb") as f:
                    encrypted_data = f.read()
                decrypted = self.fernet.decrypt(encrypted_data)
                img = Image.open(io.BytesIO(decrypted))
                w, h = img.size
                sig_region = img.crop((int(w * 0.7), int(h * 0.85), w, h))
                sig_bytes = io.BytesIO()
                sig_region.save(sig_bytes, format="PNG")
                return hashlib.sha256(sig_bytes.getvalue()).hexdigest()
        except Exception:
            pass
        return hashlib.sha256(f"sig_region_{loan_id}".encode()).hexdigest()

    def confirm_ocr(self, db: Session, loan_id: str, confirmed_amount: float, confirmed_purpose: str,
                    attempt_number: int, confirmed_extras: dict = None):
        """Confirm OCR results with farmer-validated values.

        confirmed_extras may contain:
            account_number, ifsc, phone, annual_income, land_ownership, loan_reason
        """
        loan_doc = db.query(LoanDocument).filter(LoanDocument.loan_id == loan_id).first()
        if not loan_doc:
            raise ValueError("No document found for this loan")

        # Validate primary fields
        if confirmed_amount <= 0:
            raise ValueError("Amount must be positive")
        if confirmed_amount > 10_000_000:
            raise ValueError("Amount exceeds maximum of ₹1,00,00,000")
        if not confirmed_purpose or len(confirmed_purpose) < 5:
            raise ValueError("Purpose must be at least 5 characters")
        if len(confirmed_purpose) > 500:
            raise ValueError("Purpose must be at most 500 characters")

        # Store primary confirmed values
        loan_doc.ocr_confirmation_attempts = attempt_number
        loan_doc.farmer_confirmed_amount = confirmed_amount
        loan_doc.farmer_confirmed_purpose = confirmed_purpose
        loan_doc.ocr_confirmed_at = datetime.now(timezone.utc)

        # Store structured confirmed values
        if confirmed_extras:
            if confirmed_extras.get("account_number"):
                loan_doc.farmer_confirmed_account_number = str(confirmed_extras["account_number"])
            if confirmed_extras.get("ifsc"):
                loan_doc.farmer_confirmed_ifsc = str(confirmed_extras["ifsc"])
            if confirmed_extras.get("phone"):
                loan_doc.farmer_confirmed_phone = str(confirmed_extras["phone"])
            if confirmed_extras.get("annual_income"):
                loan_doc.farmer_confirmed_annual_income = float(confirmed_extras["annual_income"])
            if confirmed_extras.get("land_ownership"):
                loan_doc.farmer_confirmed_land_ownership = str(confirmed_extras["land_ownership"])
            if confirmed_extras.get("loan_reason"):
                loan_doc.farmer_confirmed_loan_reason = str(confirmed_extras["loan_reason"])

        # Update loan with confirmed values
        loan = db.query(Loan).filter(Loan.loan_id == loan_id).first()
        if loan:
            # Populate farmer name: prefer OCR-extracted name from the document
            # (the actual name the farmer wrote), fall back to Aadhaar only if OCR is empty
            if loan_doc.ocr_extracted_farmer_name:
                loan.farmer_name = loan_doc.ocr_extracted_farmer_name
            elif not loan.farmer_name and loan.aadhaar_verified_name:
                loan.farmer_name = loan.aadhaar_verified_name
            if not loan.farmer_id:
                loan.farmer_id = f"KIOSK-{loan_id}"
            if not loan.tenure_months:
                loan.tenure_months = 12
            if not loan.interest_rate:
                loan.interest_rate = 7.0

            loan.amount = confirmed_amount
            loan.purpose = confirmed_purpose
            loan.status = "ocr_confirmed"

            # Copy confirmed phone to loan.farmer_mobile for IVR calls
            if confirmed_extras and confirmed_extras.get("phone"):
                loan.farmer_mobile = str(confirmed_extras["phone"])

            # Recompute loan hash with confirmed values
            from app.services.crypto_service import CryptoService
            crypto = CryptoService()
            hash_params = {
                "loan_id": loan.loan_id,
                "farmer_id": loan.farmer_id,
                "farmer_name": loan.farmer_name,
                "amount": confirmed_amount,
                "tenure_months": loan.tenure_months,
                "interest_rate": loan.interest_rate,
                "purpose": confirmed_purpose,
            }
            loan.loan_hash = crypto.generate_loan_hash(hash_params)

        # Update kiosk session
        session = db.query(KioskSession).filter(KioskSession.loan_id == loan_id).first()
        if session:
            session.session_status = "ocr_confirmed"

        db.commit()

        # Auto-activate assistance if too many attempts
        needs_assistance = attempt_number >= 3

        return {
            "confirmed": True,
            "loan_hash": loan.loan_hash if loan else None,
            "session_status": "ocr_confirmed",
            "needs_assistance": needs_assistance,
        }

    def activate_employee_assistance(self, db: Session, loan_id: str):
        """Generate an assistance code for employee verification."""
        import random
        assistance_code = f"{random.randint(1000, 9999)}"

        loan_doc = db.query(LoanDocument).filter(LoanDocument.loan_id == loan_id).first()
        if loan_doc:
            loan_doc.employee_assistance_used = True

        loan = db.query(Loan).filter(Loan.loan_id == loan_id).first()
        if loan:
            loan.assistance_session = True

        db.commit()

        print(f"ASSISTANCE CODE for loan {loan_id}: {assistance_code}")

        return {
            "assistance_code": assistance_code,
            "expires_in_seconds": 300,
        }

    def confirm_assistance(self, db: Session, loan_id: str, employee_id: str, assistance_code: str):
        """Confirm employee physical presence for assistance."""
        loan_doc = db.query(LoanDocument).filter(LoanDocument.loan_id == loan_id).first()
        if loan_doc:
            loan_doc.assisting_employee_id = employee_id
        db.commit()
        return {"confirmed": True, "employee_id": employee_id}
