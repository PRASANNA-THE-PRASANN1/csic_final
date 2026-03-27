"""
Migration script: Add structured OCR fields to loan_documents table.
Run: python migrate_ocr_fields.py
"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "cge_system.db")

NEW_COLUMNS = [
    # OCR extracted fields
    ("ocr_extracted_account_number", "VARCHAR(20)"),
    ("ocr_extracted_ifsc", "VARCHAR(11)"),
    ("ocr_extracted_phone", "VARCHAR(15)"),
    ("ocr_extracted_aadhaar_masked", "VARCHAR(20)"),
    ("ocr_extracted_annual_income", "FLOAT"),
    ("ocr_extracted_land_ownership", "TEXT"),
    ("ocr_extracted_loan_reason", "TEXT"),
    ("ocr_structured_fields_encrypted", "TEXT"),
    ("ocr_field_confidences_json", "TEXT"),
    ("ocr_needs_review_fields", "TEXT"),
    ("ocr_engine_used", "VARCHAR(50)"),
    ("form_photo_hash", "VARCHAR(64)"),
    ("form_photo_encrypted_path", "VARCHAR(500)"),
    # Farmer-confirmed structured fields
    ("farmer_confirmed_account_number", "VARCHAR(20)"),
    ("farmer_confirmed_ifsc", "VARCHAR(11)"),
    ("farmer_confirmed_phone", "VARCHAR(15)"),
    ("farmer_confirmed_annual_income", "FLOAT"),
    ("farmer_confirmed_land_ownership", "TEXT"),
    ("farmer_confirmed_loan_reason", "TEXT"),
    # OCR pipeline tracking
    ("ocr_source", "VARCHAR(50)"),
    ("ocr_fallback_used", "BOOLEAN DEFAULT 0"),
]


# IVR columns to add to the loans table
IVR_COLUMNS = [
    ("ivr_status", "VARCHAR(30)"),
    ("ivr_attempts", "INTEGER DEFAULT 0"),
    ("ivr_confirmed_at", "DATETIME"),
    ("consent_final_method", "VARCHAR(20)"),
    ("ivr_window_started_at", "DATETIME"),
]

# Aadhaar QR + Face Match columns to add to kiosk_presence_records table
PRESENCE_COLUMNS = [
    ("aadhaar_qr_photo_encrypted_path", "VARCHAR(500)"),
    ("aadhaar_qr_scanned_at", "DATETIME"),
    ("face_match_score", "FLOAT"),
    ("face_match_passed", "BOOLEAN"),
    ("face_match_attempts", "INTEGER DEFAULT 0"),
]


def migrate():
    if not os.path.exists(DB_PATH):
        print(f"Database not found at {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # ── Migrate loan_documents table ──
    cursor.execute("PRAGMA table_info(loan_documents)")
    existing = {row[1] for row in cursor.fetchall()}
    print(f"loan_documents existing columns: {len(existing)}")

    added = 0
    for col_name, col_type in NEW_COLUMNS:
        if col_name not in existing:
            sql = f"ALTER TABLE loan_documents ADD COLUMN {col_name} {col_type}"
            cursor.execute(sql)
            print(f"  + Added: {col_name} ({col_type})")
            added += 1
        else:
            print(f"  - Exists: {col_name}")

    # ── Migrate loans table (IVR fields) ──
    cursor.execute("PRAGMA table_info(loans)")
    existing_loans = {row[1] for row in cursor.fetchall()}
    print(f"\nloans existing columns: {len(existing_loans)}")

    ivr_added = 0
    for col_name, col_type in IVR_COLUMNS:
        if col_name not in existing_loans:
            sql = f"ALTER TABLE loans ADD COLUMN {col_name} {col_type}"
            cursor.execute(sql)
            print(f"  + Added: {col_name} ({col_type})")
            ivr_added += 1
        else:
            print(f"  - Exists: {col_name}")

    # ── Migrate kiosk_presence_records table (Aadhaar QR + Face Match) ──
    cursor.execute("PRAGMA table_info(kiosk_presence_records)")
    existing_presence = {row[1] for row in cursor.fetchall()}
    print(f"\nkiosk_presence_records existing columns: {len(existing_presence)}")

    presence_added = 0
    for col_name, col_type in PRESENCE_COLUMNS:
        if col_name not in existing_presence:
            sql = f"ALTER TABLE kiosk_presence_records ADD COLUMN {col_name} {col_type}"
            cursor.execute(sql)
            print(f"  + Added: {col_name} ({col_type})")
            presence_added += 1
        else:
            print(f"  - Exists: {col_name}")

    conn.commit()
    conn.close()
    print(f"\nMigration complete: {added} loan_documents, {ivr_added} loans IVR, {presence_added} presence columns added.")


if __name__ == "__main__":
    migrate()

