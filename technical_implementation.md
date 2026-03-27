# CGE System – Complete Technical Implementation Reference

> **Purpose**: A comprehensive, field-level logical explanation of the entire CGE System architecture. This document explains every model, service, API route, frontend page, and security mechanism so any developer or auditor can understand the code without reading the source.

---

## 1. Project Architecture Overview

The system is a **React 18 + FastAPI 0.100** application with a custom Proof-of-Work Blockchain (DB-backed), SQLite database (via SQLAlchemy ORM), Ed25519 cryptographic signing, and Twilio IVR voice verification. It facilitates secure loan origination, multi-tier approvals, and immutable audit trails for rural credit cooperative banks in India.

### Technology Stack
| Layer | Technology | Purpose |
|-------|------------|---------|
| **Frontend** | React 18, Axios, face-api.js, Recharts | SPA with RBAC routing, live biometrics |
| **Backend** | FastAPI, Uvicorn | REST API server (2910-line monolith router) |
| **Database** | SQLite + SQLAlchemy | 14 ORM models, persistent storage |
| **Cryptography** | Ed25519 (PyNaCl), Fernet (cryptography lib), SHA-256 | Signing, encryption at rest, integrity hashes |
| **OCR** | Google Cloud Vision → PaddleOCR → Tesseract → Manual | 3-layer OCR pipeline with cloud primary + offline fallback |
| **IVR** | Twilio Voice + SMS (TwiML, Amazon Polly Aditi Hindi voice) | 60-second voice consent confirmation window |
| **Blockchain** | Custom PoW chain (JSON-file backed) | Immutable consent/execution anchoring |
| **Auth** | JWT HS256 (python-jose), bcrypt (passlib) | Session tokens, password hashing |

### Runtime Architecture
```
┌─────────────┐    ┌─────────────┐    ┌──────────────┐
│  React SPA  │───>│  FastAPI     │───>│  SQLite DB   │
│  :3000      │    │  :8000      │    │  (14 tables) │
│  face-api.js│    │  Ed25519/   │    └──────────────┘
│             │    │  Fernet/JWT │    ┌──────────────┐
│             │    │             │───>│  Blockchain   │
│             │    │  OCR Pipeline│   │  (JSON file) │
│             │    │  IVR/Twilio │    └──────────────┘
│             │    │  Google OCR │    ┌──────────────┐
└─────────────┘    └─────────────┘    │  Twilio API  │
                                      │  Google Cloud│
                                      └──────────────┘
```

### Implemented Enhancement Modules
- **Kiosk Mode**: 15-component sessionless farmer-facing tablet interface for secure onboarding with mandatory employee assistance. 11-step flow: start → terms → Aadhaar QR → presence → face match → Aadhaar OTP → form instructions → document upload → OCR confirm → consent → receipt.
- **IVR Voice Confirmation**: Twilio-powered voice call + SMS fallback with a mandatory 60-second window. Hindi TTS via Amazon Polly Aditi. 3-attempt DTMF retry loop. Farmer presses 1 (confirm) or 2 (reject). Auto-completes kiosk session on confirmation. Frontend polls every 2 seconds with server-synced countdown.
- **Multi-Factor Fraud Prevention**: Active liveness challenges (blink, head turn, smile), face-api.js client-side detection, device fingerprinting, GPS tracking, OTP verification.
- **3-Layer OCR Pipeline**: Layer 1 — Google Cloud Vision (cloud, primary). Layer 2 — Local PaddleOCR/Tesseract (offline fallback). Layer 3 — Manual entry signal (never crashes). All three layers feed into the same 9-field extraction + validation + confidence scoring pipeline.
- **Clerk Verification**: Bank staff review of OCR vs farmer-confirmed data, Aadhaar evidence, biometric evidence, 60-second minimum review timer.
- **Manager Rejections**: Cryptographically signed rejection flows at approval, CBS validation, and disbursement stages with dashboard statistics.
- **Disbursement Rejection**: Separate rejection pathway for loans already in `cbs_validated` or `ready_for_execution` status.
- **CBS Validation**: Core Banking System mock integration with NPA checks, eligibility scoring, and ledger/balance queries.
- **Override Governance**: CEO + Auditor dual-signature emergency override mechanism with blockchain anchoring.
- **Fernet Encryption**: Secure storage of all PII — photos, Aadhaar documents, and OCR field data encrypted at rest using `MASTER_KEY`.
- **Consent Certificate**: Full cryptographic certificate aggregating all lifecycle events for a loan.

---

## 2. Complete Loan Status Lifecycle

The loan traverses the following status state machine:

```
kiosk_started → aadhaar_verified → document_uploaded → ocr_confirmed
    → kiosk_consented → [IVR GATE: 60s voice/SMS confirmation]
    → kiosk_anchored → pending_clerk_review
    → pending_approvals → cbs_validated → ready_for_execution
    → executed → anchored

IVR confirmation branch (mandatory after kiosk_consented):
    kiosk_consented → ivr_status=pending → ivr_status=confirmed → kiosk_anchored
    kiosk_consented → ivr_status=pending → ivr_status=rejected → kiosk_rejected
    kiosk_consented → ivr_status=pending → ivr_status=timed_out → kiosk_rejected
    kiosk_consented → ivr_status=pending → ivr_status=failed → SMS fallback

Rejection branches:
    pending_clerk_review → clerk_rejected
    pending_approvals → manager_rejected
    cbs_validated → manager_rejected | disbursement_rejected
    ready_for_execution → manager_rejected | disbursement_rejected
    kiosk_started → kiosk_expired (timeout)
    kiosk_consented → kiosk_rejected (IVR timeout/rejection)
```

---

## 3. Database Models (SQLAlchemy ORM)
Located in `backend/app/models/`. 14 tables total.

### 3.1 Loan (`loan.py`) — Central Entity
The `Loan` model has **40+ columns** organized into logical groups:

| Field Group | Columns | Purpose |
|-------------|---------|---------|
| **Identity** | `loan_id` (LN{ts}), `farmer_id`, `farmer_name`, `farmer_mobile` | Core farmer linkage |
| **Financials** | `amount`, `tenure_months`, `interest_rate`, `purpose` | Loan parameters |
| **Declaration** | `declaration_id` (FK), `farmer_declared_amount`, `amount_difference_reason`, `amount_verified_by_senior` | Fraud Type 2 — Amount Inflation prevention |
| **Integrity** | `loan_hash` (SHA-256), `status`, `approval_tier` (tier_1–4) | Tamper detection + state machine |
| **Kiosk Session** | `kiosk_session_id`, `aadhaar_verified_name`, `document_hash`, `kiosk_phase_anchor_hash`, `kiosk_completed_at`, `assistance_session` | Links to kiosk phase data |
| **IVR Confirmation** | `ivr_status` (pending/confirmed/rejected/failed/timed_out), `ivr_attempts`, `ivr_confirmed_at`, `consent_final_method` (ivr/sms), `ivr_window_started_at` | 60-second voice consent confirmation window |
| **Clerk Review** | `clerk_reviewed_by`, `clerk_accepted_at`, `clerk_rejected_at`, `clerk_review_opened_at`, `rejection_reason`, `rejection_category` | Track clerk decision with timing |
| **Manager Rejection** | `manager_rejected_by`, `manager_rejected_by_name`, `manager_rejected_by_role`, `manager_rejection_reason`, `manager_rejection_category`, `manager_rejected_at`, `manager_rejection_signature` | Ed25519-signed rejection evidence |
| **Employee** | `assisting_employee_name`, `assisting_employee_id` | Mandatory kiosk employee tracking |
| **CBS** | `cbs_validated_at` | Core Banking System validation timestamp |
| **Metadata** | `metadata_json` (JSON), `created_at`, `updated_at`, `created_by` | Extensible metadata store |

**Relationships**: `farmer_consent` (1:1), `approvals` (1:N), `blockchain_anchor` (1:1), `disbursement_consent` (backref), `notifications` (backref), `override_requests` (backref).

### 3.2 KioskPresenceRecord (`kiosk_presence.py`) — Physical Presence Evidence
Records all physical presence evidence collected during the kiosk phase:

| Field Group | Columns |
|-------------|---------|
| **GPS** | `gps_latitude`, `gps_longitude`, `gps_captured_at` |
| **Photo** | `photo_hash` (SHA-256), `photo_encrypted_storage_path`, `photo_captured_at` (server-authoritative) |
| **Aadhaar** | `aadhaar_last_four`, `aadhaar_hash` (SHA-256 of full number), `aadhaar_verified_name`, `aadhaar_otp_verified`, `aadhaar_verified_at` |
| **Device** | `device_fingerprint` (JSON), `device_fingerprint_hash` (SHA-256) |
| **Terms** | `terms_accepted_at`, `terms_scroll_completed` |
| **Passive Liveness** | `face_detected_client_side`, `liveness_check_suspicious` |
| **Active Liveness** | `active_liveness_passed`, `liveness_blink_detected`, `liveness_head_turn_detected`, `liveness_smile_detected`, `liveness_challenges_json` (full challenge + server validation + extended liveness + multi-face results) |
| **Framing** | `face_count_client`, `face_centered`, `auto_captured` |
| **Employee** | `assisting_employee_name`, `assisting_employee_id` |

### 3.3 KioskSession (`kiosk_session.py`) — Session Lifecycle
Tracks ephemeral 30-minute kiosk sessions with mandatory employee assignment:
- `session_id` (UUID), `loan_id` (1:1), `session_token` (128-char random), `session_token_expires_at`
- `session_status`: `started` → `aadhaar_verified` → `document_uploaded` → `ocr_confirmed` → `consented` → `completed` | `expired`
- `assisting_employee_name`, `assisting_employee_id` — mandatory at session creation
- `ip_address`, `kiosk_device_fingerprint`

### 3.4 LoanDocument (`loan_document.py`) — Document + OCR Evidence
Stores document hashes, OCR extraction results, and farmer confirmations. **28+ columns**:

| Field Group | Columns |
|-------------|---------|
| **Document** | `document_hash` (SHA-256 of raw bytes, immutable), `signature_region_hash`, `encrypted_document_path` |
| **Legacy OCR** | `ocr_extracted_amount`, `ocr_extracted_purpose`, `ocr_extracted_farmer_name`, `ocr_confidence_score` |
| **Structured OCR** | `ocr_extracted_account_number`, `ocr_extracted_ifsc`, `ocr_extracted_phone`, `ocr_extracted_aadhaar_masked` (XXXX-XXXX-1234), `ocr_extracted_annual_income`, `ocr_extracted_land_ownership`, `ocr_extracted_loan_reason` |
| **OCR Metadata** | `ocr_structured_fields_encrypted` (Fernet-encrypted full JSON), `ocr_field_confidences_json` (per-field confidence), `ocr_needs_review_fields` (comma-separated), `ocr_engine_used` (paddleocr/tesseract/google_vision), `form_photo_hash`, `form_photo_encrypted_path` |
| **OCR Pipeline Tracking** | `ocr_source` (google_vision/paddleocr/tesseract/manual — which layer succeeded), `ocr_fallback_used` (boolean — True if Google Vision failed and local OCR used) |
| **Farmer Confirmed** | `farmer_confirmed_amount`, `farmer_confirmed_purpose`, `farmer_confirmed_account_number`, `farmer_confirmed_ifsc`, `farmer_confirmed_phone`, `farmer_confirmed_annual_income`, `farmer_confirmed_land_ownership`, `farmer_confirmed_loan_reason` |
| **Process** | `ocr_confirmation_attempts`, `ocr_confirmed_at`, `document_uploaded_at`, `employee_assistance_used`, `assisting_employee_id` |

### 3.5 ConsentOTPRecord (`consent_otp.py`) — OTP Audit Trail
Tracks OTP issuance and verification for both Aadhaar authentication and loan consent. Never stores raw OTP values:
- `loan_id` (FK), `otp_type` (`aadhaar_auth` | `loan_consent`), `otp_hash` (SHA-256 of OTP value)
- `otp_reference_id` (unique), `mobile_last_four`, `issued_at`, `expires_at` (10 min)
- `verified_at`, `used` (boolean), `attempt_count`

### 3.6 FarmerConsent (`consent.py`) — Cryptographic Consent Proof
Links farmer's cryptographic agreement to exact loan terms:
- `loan_hash`, `farmer_signature` (Base64 Ed25519), `consent_method` (`bank_kyc_otp_local_biometric` | `bank_kyc_otp`)
- `otp_verified` (last 4 digits), `consent_token` (full JSON metadata)
- `bank_kyc_verified`, `otp_reference_id`, `fingerprint_hash`, `fingerprint_captured_at`
- `live_photo_hash`, `gps_latitude`, `gps_longitude`, `consent_device_fingerprint`

### 3.7 Approval (`approval.py`) — Manager Approval Signature
Records each manager's individual cryptographic approval:
- `approver_id`, `approver_name`, `approver_role` (branch_manager/credit_manager/ceo/board_member)
- `loan_hash` (must match `loan.loan_hash`), `approver_signature` (Base64 Ed25519)
- `comments`, `approved_at`, `ip_address`

### 3.8 Remaining Models

| Model | File | Key Fields | Purpose |
|-------|------|------------|---------|
| **BlockchainAnchor** | `blockchain.py` | `consent_hash`, `block_number`, `transaction_hash`, `blockchain_response` | Links loan to immutable PoW chain |
| **DisbursementConsent** | `disbursement.py` | `account_number`, `account_holder_name`, `ifsc_code`, `penny_drop_verified`, `penny_drop_name_matched`, `penny_drop_response`, `disbursement_hash`, `farmer_disbursement_signature` | Benami fraud prevention via penny-drop |
| **FarmerDeclaration** | `declaration.py` | `farmer_id`, `declared_amount`, `purpose`, `declaration_hash`, `declaration_signature`, `otp_verified`, `status` | Amount Inflation fraud prevention |
| **Notification** | `notification.py` | `notification_type` (loan_creation/consent_confirmation/disbursement), `recipient_mobile`, `sms_content`, `delivery_status`, `sms_gateway_response` | SMS audit trail — proves farmer was informed |
| **UsedNonce** | `nonce.py` | `nonce` (unique, 64-char), `loan_id` | Replay attack prevention |
| **User** | `user.py` | `user_id`, `name`, `role` (7 roles), `password_hash` (bcrypt) | RBAC identity |
| **OverrideRequest** | `override.py` | `requested_by` (CEO), `co_signed_by` (Auditor), `ceo_signature`, `auditor_signature`, `reason_text`, `status` (pending_cosign/approved/rejected), `anchor_block_id` | Emergency dual-signature governance |

---

## 4. Backend Services (Business Logic)
Located in `backend/app/services/`. **19 service files**.

### 4.1 OCR Pipeline (`ocr_service.py` — 970 lines)
The most complex service. Implements a **fully offline 6-step OCR pipeline**:

**Step 1 — Image Preprocessing** (`ImagePreprocessor`):
- OpenCV-based pipeline: grayscale → bilateral filter denoising → adaptive Gaussian threshold → morphological opening → Hough line deskewing
- Handles handwritten forms with uneven lighting

**Step 2 — Text Recognition** (`TextRecognizer`):
- **Primary**: PaddleOCR with 6 parameter set fallbacks for version 2.x/3.x compatibility. Environment variable `PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK` skips slow connectivity checks. Hindi+English language support.
- **Fallback**: Tesseract OCR with Windows path auto-detection (checks `C:\Program Files\Tesseract-OCR\`) and Hindi+English → English-only fallback.
- Returns structured output: `{engine, full_text, lines[], words[], avg_confidence}`

**Step 3 — Field Extraction** (`FieldExtractor`):
- Extracts 9 structured fields using regex + heuristic label matching:
  1. `name` — Hindi/English label patterns (नाम, applicant name, etc.)
  2. `account_number` — 9-18 digit sequences, label-adjacent or regex scan
  3. `ifsc` — Pattern `[A-Z]{4}0[A-Z0-9]{6}`
  4. `phone_number` — Indian mobile: `[6-9]\d{9}`
  5. `aadhaar_number` — 12 digits with space/dash tolerance, excludes 0/1 prefix
  6. `loan_amount` — Currency-prefixed amounts near labels (₹, Rs.)
  7. `annual_income` — Same currency extraction near income labels
  8. `land_ownership` — Acre/hectare/bigha patterns
  9. `loan_reason` — Label-adjacent text extraction
- Multi-line support: checks label on one line, value on next

**Step 3b — Optional LLM Enhancement** (`LLMFieldExtractor`):
- Connects to local Ollama (Mistral model) at `http://localhost:11434`
- Sends raw OCR text with structured prompt for JSON extraction
- Merges LLM results into regex results, filling gaps where regex found nothing

**Step 4 — Validation** (`FieldValidator`):
- `name`: minimum 2 chars, no digits
- `account_number`: 9-18 digits
- `ifsc`: ABCD0XXXXXX format
- `phone`: exactly 10 digits starting with 6-9
- `aadhaar_number`: 12 digits, not starting with 0/1, **Verhoeff checksum** validation (full D/P lookup tables implemented)
- `loan_amount`: positive, max ₹1,00,00,000
- `annual_income`: positive number
- `land_ownership` / `loan_reason`: minimum length checks

**Step 5 — Confidence Scoring** (`ConfidenceScorer`):
- Weighted combination: OCR confidence (0.4) + extraction method weight (0.45) + validation bonus (0.15)
- Method weights: label_match=0.8, regex_pattern=0.7, llm_extract=0.75, regex_scan=0.4
- Fields with confidence < 0.6 are flagged `needs_review`

**Step 6 — Orchestration** (`OCRService`):
- `process_document(image_bytes)` runs the full pipeline
- `mask_aadhaar()` produces XXXX-XXXX-1234 format
- `encrypt_fields()` uses Fernet to encrypt all field data before storage

### 4.2 Photo Verification (`photo_verification_service.py` — 443 lines)
Handles server-side image quality validation, liveness detection, encrypted storage, and retrieval:

- **Image Quality** (4 checks): file size (5KB-5MB), valid image format (PIL verify), minimum dimensions (200x200), uniformity detection (std_dev < 15 = suspicious blank/covered camera)
- **Passive Liveness** (3-frame): mean absolute pixel difference between sequential frames. Variance < 8 = suspicious static image.
- **Active Liveness** (5-frame, layered verification model):
  - Timestamp validation: each challenge must take 0.5s-30s
  - Frame variance: challenge frames must show MORE movement than baseline
  - Per-challenge verification: blink (brightness dip), head turn (>3.0 variance), smile (>1.5 variance)
  - Suspicious flags: `INCOMPLETE_CHALLENGES`, `TOO_FAST_*`, `LOW_CHALLENGE_VARIANCE`, `BLINK_NO_FRAME_CHANGE`, etc.
- **Multi-face Detection**: RGB skin-color segmentation across quadrants. Skin in 3+ quadrants = multi-face suspected.
- **Extended Liveness** (N-frame): pairwise variance across all adjacent frames, with replay detection (identical variance range + high avg = looped video).
- **Encrypted Storage**: Length-prefixed frame concatenation → Fernet encryption → `data/photos/{loan_id}.enc`
- **Decryption/Retrieval**: Reverse process with length-prefix parsing for individual frame extraction.

### 4.3 Consent Engine (`consent_engine.py` — 496 lines)
Orchestrates the complete consent and approval lifecycle:

**`create_farmer_consent()`**:
- Validates status is `pending_farmer_consent`, no duplicate consent, OTP is exactly 6 digits
- Signs `loan_hash` with farmer's Ed25519 key
- Builds comprehensive consent token with metadata (IP, device, OTP last 4, GPS, biometric flags)
- Transitions loan to `pending_approvals`

**`create_manager_approval()`**:
- Validates status is `pending_approvals` or `approved`
- Enforces role requirement via `PolicyEngine.is_role_required()`
- Prevents duplicate approvals (same approver or same role)
- Signs `loan_hash` with approver's Ed25519 key
- Auto-transitions to `ready_for_execution` when all policy requirements met

**`validate_execution_eligibility()`** — 8-step pre-execution gauntlet:
1. **Kiosk Session Completeness** (5 sub-checks):
   - 0a: `KioskSession.session_status == "completed"`
   - 0b: `KioskPresenceRecord.aadhaar_otp_verified == True`
   - 0c: `LoanDocument.ocr_confirmed_at IS NOT NULL`
   - 0d: `ConsentOTPRecord` of type `loan_consent` with `used == True`
   - 0e: `loan.kiosk_phase_anchor_hash IS NOT NULL`
2. **Hash Integrity**: Recompute SHA-256 from 7 loan params, compare against stored `loan_hash`
3. **Farmer Consent**: Verify consent hash matches, verify Ed25519 signature
4. **Manager Approvals**: Verify each approval's hash + signature individually
5. **Policy Compliance**: `PolicyEngine.validate_approvals()` — all required roles present
6. **Disbursement Consent**: Penny-drop verification must be complete
7. **SMS Notification Verification**: `loan_creation` + `consent_confirmation` notifications must exist and not be `failed`
8. **Time-based Validation**: Warning if approval < 5 min after consent (rush fraud), block if > 30 days (stale consent)

### 4.4 Cryptography & Integrity (`crypto_service.py` — 8KB)
- `generate_key_pair()`: Auto-generates Ed25519 keys in `data/keys/`, encrypted at rest with Fernet
- `sign_data()` / `verify_signature()`: Every state change requires signing the immutable `loan_hash`
- `generate_loan_hash()`: Canonical JSON serialization → SHA-256 from 7 parameters
- `generate_consent_token()`: Creates comprehensive consent metadata JSON
- `generate_final_consent_token()`: Execution-time token aggregating all events
- Symmetric Fernet encryption via `MASTER_KEY` environment variable

### 4.5 Blockchain (`blockchain_service.py` — 7.9KB)
- DB-backed PoW chain stored in `blockchain/blockchain_data.json`
- `anchor_consent()`: Hashes the final approved/executed JSON token, adds to chain with nonce-based PoW
- `verify_chain_integrity()`: Recalculates sequential hashes to detect chain tampering
- `verify_loan_anchor()`: Verifies a specific loan's blockchain anchor
- `verify_full_chain()`: Full chain integrity check

### 4.6 Policy Engine (`policy_engine.py` — 6.5KB)
Defines strict hardcoded tier limitations:

| Tier | Amount Range | Required Approvals |
|------|-------------|-------------------|
| **Tier 1** | ≤ ₹50,000 | Branch Manager |
| **Tier 2** | ₹50,001 – ₹2,00,000 | Branch Manager + Credit Manager |
| **Tier 3** | ₹2,00,001 – ₹10,00,000 | Branch Manager + Credit Manager + CEO |
| **Tier 4** | > ₹10,00,000 | Branch Manager + Credit Manager + CEO + Board Member |

Functions: `determine_tier()`, `validate_loan()`, `get_required_approvals()`, `get_missing_approvals()`, `is_role_required()`, `get_tier_info()`, `validate_approvals()`.

### 4.7 Document Service (`document_service.py` — 23KB)
- `receive_document()`: Hashes raw bytes (SHA-256), encrypts + stores, updates `LoanDocument`
- `run_ocr()`: **3-layer OCR orchestration pipeline**:
  - **Layer 1 — Google Cloud Vision** (primary): Calls `GoogleVisionOCR.extract_text()`, feeds raw text into the existing `FieldExtractor` → `FieldValidator` → `ConfidenceScorer` pipeline for 9-field structured extraction. On success, sets `ocr_source='google_vision'`, `ocr_fallback_used=False`
  - **Layer 2 — Local PaddleOCR/Tesseract** (fallback): If Layer 1 fails (no credentials, network error, timeout), falls through to `OCRService.process_document()` which runs the full 6-step offline pipeline. Sets `ocr_source='paddleocr'/'tesseract'`, `ocr_fallback_used=True`
  - **Layer 3 — Manual entry signal** (final fallback): If both OCR layers fail, returns `manual_required=True` with all 9 fields flagged `needs_review`. Sets `ocr_source='manual'`. The frontend displays a manual entry form — the flow **never crashes**
- Photo box extraction: Crops face region from document using `FormRegionExtractor`, hashes + encrypts + stores separately
- `confirm_ocr()`: Saves farmer-confirmed values for all structured fields, copies confirmed phone to `loan.farmer_mobile` for IVR, recomputes `loan_hash`, increments attempt count. **Name priority**: Uses OCR-extracted farmer name from the document as the canonical `loan.farmer_name`; Aadhaar-verified name is only used as a fallback if OCR didn't extract a name
- `activate_employee_assistance()`: Flags document for assisted processing
- `confirm_assistance()`: Clerk confirms physical presence during assisted session

### 4.8 Kiosk Services

| Service | File | Size | Purpose |
|---------|------|------|---------|
| **KioskSessionService** | `kiosk_session_service.py` | 5.3KB | Session lifecycle: create (with employee), validate token, update activity, complete, expire |
| **KioskConsentService** | `kiosk_consent_service.py` | 6.6KB | Bundle OTP + face liveness + Aadhaar signals into signed consent. Initiate/verify consent OTP. After OTP verification, triggers IVR voice call |
| **KioskAnchorService** | `kiosk_anchor_service.py` | 1.7KB | Create intermediate blockchain anchor for the kiosk initiation step |

### 4.9 IVR Voice Confirmation Service (`ivr_service.py` — 10.6KB)
Handles Twilio voice calls and SMS fallback for the mandatory 60-second consent confirmation window:

**`_build_voice_twiml(loan_id, loan_amount)`** — Generates TwiML XML:
- Uses **Amazon Polly Aditi** voice (`voice="Polly.Aditi"`, `language="hi-IN"`) for native Hindi text-to-speech
- **Hindi preamble**: "नमस्ते। यह कॉल आपके बैंक ऋण आवेदन की पुष्टि के लिए है।"
- **3-attempt `<Gather>` retry loop**: Each attempt plays the loan amount and asks farmer to press 1 (confirm) or 2 (reject), with `numDigits=1`, `timeout=10`. If no input after 10 seconds, TwiML falls through to retry prompt and next Gather
- After 3 failed attempts: plays a final "no input" message and hangs up
- Gather `action` URL points to `{VOICE_WEBHOOK_BASE_URL}/api/ivr/webhook?loan_id=...` (must be publicly reachable by Twilio)

**`trigger_ivr_call(db, loan_id, farmer_phone, loan_amount)`**:
- Sets `ivr_status='pending'`, increments `ivr_attempts`, records `ivr_window_started_at`
- Places call via `twilio.rest.Client.calls.create()` with inline `twiml=` parameter
- Configures `status_callback` for call completion/failure events
- **Simulation mode**: If Twilio client unavailable (no credentials), logs the call + prints curl command for manual webhook testing
- On call failure, automatically triggers `trigger_sms_fallback()`

**`trigger_sms_fallback(db, loan_id, farmer_phone, loan_amount)`**:
- Sends "Reply YES/NO" SMS via Twilio with `status_callback` pointing to `/api/ivr/sms-webhook`

**`check_ivr_timeout(db, loan)`**: Checks if 60-second window expired. If expired and status still `pending`, sets `ivr_status='timed_out'` and rejects the loan

**`is_within_window(loan)`**: Returns True if current time is within 60 seconds of `ivr_window_started_at` (timezone-aware)

**`reject_loan(db, loan)`**: Sets `status='kiosk_rejected'`, expires the kiosk session

### 4.10 Google Cloud Vision OCR (`external_ocr_service.py` — 5.6KB)
Layer 1 of the OCR pipeline. A lightweight wrapper around Google Cloud Vision's `document_text_detection` API:

- **Lazy client initialization**: Reads service account credentials from `GOOGLE_VISION_CREDENTIALS_PATH` env var or default `backend/google_vision_credentials.json`. Uses `google.oauth2.service_account.Credentials`
- **`is_available()`**: Class method that checks if credentials are present and client can initialize. Called before attempting Layer 1 OCR
- **`extract_text(image_bytes)`**: Calls `document_text_detection()` with 10-second timeout per attempt, max 2 retries. Returns full text string from `full_text_annotation.text`
- **Error handling**: Raises `GoogleVisionError` on any failure (auth, network, timeout, empty result). The caller (`document_service.run_ocr()`) catches this and falls through to Layer 2
- **Security**: Does NOT log raw OCR text (privacy requirement). Only logs character count

### 4.11 Integration Services (Simulated)

| Service | File | Purpose |
|---------|------|---------|
| **AadhaarService** | `aadhaar_service.py` (5.9KB) | Simulates UIDAI OTP auth: `initiate_auth()` creates `ConsentOTPRecord` with hashed OTP, `verify_auth()` checks hash + expiry + attempt count, stores verified name to presence/loan/session |
| **IdentityService** | `identity_service.py` (9.6KB) | Bank KYC database lookup: farmer identity verification, mobile number matching, consent OTP issuance/verification, device fingerprint verification |
| **PennyDropService** | `penny_drop_service.py` (4.9KB) | Simulates ₹1 deposit to farmer's account + fuzzy name matching (difflib) between account holder and farmer name |
| **CBSService** | `cbs_service.py` (2.7KB) | Core Banking System mock: ledger checks, NPA flag, eligibility scoring, balance queries |
| **NotificationService** | `notification_service.py` (8.8KB) | Format + record all SMS notifications (loan_creation, consent_confirmation, disbursement) with delivery tracking |
| **SMSService** | `sms_service.py` (3.3KB) | Raw HTTP mock client, prints to terminal console during development |
| **OverrideService** | `override_service.py` (5.6KB) | CEO creates override → Auditor co-signs → blockchain anchor created for the override itself |

---

## 5. API Layer (FastAPI Router)
Located in `backend/app/api/routes.py` (**2910 lines**), `deps.py`, `kiosk_deps.py`.

### 5.1 Security Mechanisms

| Mechanism | Implementation | Scope |
|-----------|---------------|-------|
| **JWT HS256** | python-jose, 8-hour expiry | All authenticated endpoints |
| **bcrypt** | passlib.hash.bcrypt | Password verification |
| **Idempotency** | Duplicate checks on consent, disbursement, approval endpoints | §2.6 — returns 409 |
| **Nonce Replay** | `UsedNonce` table, checked before consent creation | §2.8 |
| **OTP Rate Limit** | 3 OTPs per 10 min per mobile (in-memory) | §2.7 |
| **Kiosk Rate Limit** | 10 sessions/hour/IP, 3 OTPs/30min/loan | In-memory defaultdict |
| **Global Error Handler** | UUID request_id, no traceback exposure | §2.5 |
| **RBAC** | `require_roles()` dependency injection | Per-endpoint role gates |

### 5.2 Complete Endpoint Map (30+ endpoints across 15 sections)

#### §1 — Loan Endpoints
| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| POST | `/api/loans/create` | Any | Create loan, compute hash, determine tier, link declaration, send SMS |
| GET | `/api/loans/pending-review` | Clerk | List `pending_clerk_review` loans with farmer-confirmed amounts from LoanDocument |
| GET | `/api/loans/{loan_id}/review-detail` | Clerk | Full read-only loan record; records `clerk_review_opened_at` on first open |
| POST | `/api/loans/{loan_id}/clerk-accept` | Clerk | Accept loan → `pending_approvals`. **Enforces 60-second minimum review time** |
| POST | `/api/loans/{loan_id}/clerk-reject` | Clerk | Reject with reason (≥20 chars) + category from 6 predefined categories |
| GET | `/api/loans/{loan_id}` | Any | Single loan lookup |
| GET | `/api/loans` | Any | List with optional filters: status, farmer_id, created_by |

#### §2 — Farmer Consent
| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| POST | `/api/loans/{loan_id}/farmer-consent` | Any | Create consent with nonce replay protection + idempotency check |

#### §2b — Disbursement Consent (Fraud Type 1)
| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| POST | `/api/loans/{loan_id}/disbursement-consent` | Any | Penny-drop verification + name fuzzy match. Blocks if name doesn't match |

#### §2c — Farmer Declaration (Fraud Type 2)
| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| POST | `/api/farmer-declaration` | Any | Self-declared amount + purpose with hash + Ed25519 signature |
| GET | `/api/farmer-declaration/{id}` | Any | Lookup |

#### §3 — Manager Approval + Rejection
| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| POST | `/api/loans/{loan_id}/approve` | Any | Manager approval with Ed25519 signature; auto-transitions when policy complete |
| GET | `/api/loans/{loan_id}/approvals` | Any | List approvals + missing/required roles |
| POST | `/api/loans/{loan_id}/manager-reject` | Manager roles | Reject at approval stage. Ed25519 signed. Min 30-char reason + 8 categories |
| POST | `/api/loans/{loan_id}/disbursement-reject` | Manager roles | Reject at CBS/execution stage. Separate 7 categories. Sends rejection SMS |

#### §4 — Execution
| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| POST | `/api/execute-loan?loan_id=` | Any | 8-step eligibility validation → status `executed` → blockchain anchor → status `anchored` |

#### §5 — Audit
| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/api/audit/{loan_id}` | Any | 7-check verification: hash integrity, farmer sig, manager sigs, policy, notifications, blockchain, rejection sig |

#### §6 — Blockchain
| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/api/blockchain/chain` | Any | Full chain dump |
| GET | `/api/blockchain/verify` | Any | Full chain integrity check |
| GET | `/api/blockchain/verify-loan/{loan_id}` | Any | Single loan anchor verification |

#### §7-8 — Policy & Auth
| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/api/policy/tier-info?amount=` | Any | Tier info for amount |
| POST | `/api/auth/login` | None | bcrypt password → JWT HS256 (8h expiry) |
| GET | `/api/auth/me` | JWT | Verify token, return user info |

#### §9 — Identity Verification
| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| POST | `/api/identity/verify` | Any | Bank KYC farmer identity verification |
| POST | `/api/identity/send-otp` | Any | Rate-limited (3/10min/mobile) OTP |
| POST | `/api/identity/verify-otp` | Any | OTP verification |
| POST | `/api/identity/capture-biometric` | Any | Device fingerprint (Canvas+WebGL+Screen hash) |

#### §10-12 — Notifications, CBS, Dashboard
| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/api/loans/{loan_id}/notifications` | Any | Full notification audit trail |
| POST | `/api/cbs/validate-loan/{loan_id}` | Any | CBS validation: NPA check, eligibility, stores CBS_REF_ID in metadata |
| GET | `/api/dashboard/stats` | Any | Regulatory dashboard: status counts, fraud detection stats, blockchain integrity, kiosk ops (started/completed/expired today, avg duration, assistance rate, Aadhaar success rate, OCR retry rate), manager rejection stats by category |

#### §13 — Override Governance
| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| POST | `/api/loans/{loan_id}/override?reason=` | CEO | Create override request with Ed25519 signature |
| POST | `/api/loans/{loan_id}/override/cosign` | Auditor | Co-sign override; creates blockchain anchor |
| GET | `/api/loans/{loan_id}/overrides` | Any | List all override requests |

#### §14 — Consent Certificate
| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/api/loans/{loan_id}/consent-certificate` | Any | Full cryptographic certificate with hash of entire certificate, CBS info, all events |

#### Kiosk Phase Endpoints (Session Token Auth)
| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| POST | `/api/kiosk/start` | None | Create session with mandatory employee. Rate limited: 10/hour/IP |
| POST | `/api/kiosk/{id}/terms/accept` | Session Token | Accept T&C (requires `scroll_completed`) |
| POST | `/api/kiosk/{id}/presence/photo` | Session Token | Upload 3-5 frames + GPS + device fingerprint + liveness challenges. Full server-side validation |
| POST | `/api/kiosk/{id}/aadhaar/initiate` | Session Token | Start Aadhaar OTP auth. Rate limited: 3/30min/loan |
| POST | `/api/kiosk/{id}/aadhaar/verify` | Session Token | Verify Aadhaar OTP |
| POST | `/api/kiosk/{id}/document/upload` | Session Token | Upload + hash + encrypt document (max 10MB) |
| POST | `/api/kiosk/{id}/document/ocr` | Session Token | Run OCR pipeline on uploaded document |
| POST | `/api/kiosk/{id}/document/confirm` | Session Token | Confirm OCR with farmer-validated structured fields |
| POST | `/api/kiosk/{id}/consent/initiate` | Session Token | Generate consent OTP. Rate limited |
| POST | `/api/kiosk/{id}/consent/verify` | Session Token | Verify consent OTP, create consent event, **trigger IVR voice call** to farmer phone |
| POST | `/api/kiosk/{id}/complete` | Session Token | **Gated on IVR** — `ivr_status` must be `confirmed`. Anchor on blockchain → `pending_clerk_review` |
| POST | `/api/kiosk/{id}/assistance/request` | Session Token | Request employee assistance |
| GET | `/api/kiosk/status/{id}` | None | Public status for receipt QR codes (limited info) |
| GET | `/api/kiosk/{id}/status` | Optional Token | Session status for polling |
| GET | `/api/kiosk/{id}/evidence` | JWT (Clerk/Audit) | Complete kiosk evidence package |
| POST | `/api/kiosk/{id}/assistance/confirm` | JWT (Clerk) | Clerk confirms physical presence for assisted session |

#### §15 — IVR Voice Confirmation (Public Webhooks)
| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| POST | `/api/ivr/webhook?loan_id=` | None (Twilio) | **DTMF digit handler**. Digit 1 → `ivr_status=confirmed` + auto-complete kiosk. Digit 2 → `ivr_status=rejected` + loan rejected. Invalid → SMS fallback. Entire handler wrapped in try/except — always returns valid **TwiML XML** with Polly.Aditi Hindi voice. Uses **commit-first pattern** (status committed before auto-complete attempt) |
| POST | `/api/ivr/sms-webhook?loan_id=` | None (Twilio) | SMS reply handler. "YES" → confirmed, "NO" → rejected. Same commit-first pattern + auto-complete |
| POST | `/api/ivr/call-status?loan_id=` | None (Twilio) | Call status callback. On `busy`/`no-answer`/`failed`/`canceled` → triggers SMS fallback if `ivr_status` still `pending` |
| GET | `/api/kiosk/{loan_id}/ivr-status` | Session Token | **Frontend polling endpoint**. Returns `ivr_status`, `remaining_seconds`, `consent_final_method`. Enforces 60-second timeout on every poll. Polled by frontend every 2 seconds |

#### Audit: Asset Retrieval
| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/api/audit/kiosk-photo/{loan_id}` | Auditor/CEO/Clerk | Decrypt + return kiosk photo (JPEG or JSON with all frames as base64). Every access logged |
| GET | `/api/audit/kiosk-document/{loan_id}` | Auditor/CEO/Clerk | Decrypt + return kiosk document (auto-detect JPEG/PNG/PDF). Every access logged |

### 5.3 Schemas (`backend/app/schemas/`)
Pydantic models for request/response validation:

| File | Models |
|------|--------|
| `loan_schemas.py` | `LoanCreate` (farmer_id, amount, tenure, interest, purpose, declaration_id, etc.), `LoanResponse`, `LoanListResponse` |
| `consent_schemas.py` | `FarmerConsentCreate` (otp, nonce, device_info, live_photo_base64, GPS, fingerprint, etc.), `FarmerConsentResponse` |
| `approval_schemas.py` | `ApprovalCreate` (approver_id, approver_name, approver_role, comments), `ApprovalResponse` |
| `disbursement_schemas.py` | `DisbursementConsentCreate` (account_number, ifsc_code, account_holder_name), `DisbursementConsentResponse` |
| `declaration_schemas.py` | `FarmerDeclarationCreate`, `FarmerDeclarationResponse` |
| `auth_schemas.py` | `LoginRequest` (user_id, password), `LoginResponse` (user_id, name, role, token) |

### 5.4 Dependencies (`deps.py`, `kiosk_deps.py`)
- `deps.py`: FastAPI dependency injection generators — `get_db()` (SQLAlchemy session), `get_current_user()` (JWT validation), `require_roles()` (RBAC gate), plus factory functions for all 12 service classes
- `kiosk_deps.py`: Specialized dependency for validating kiosk session tokens instead of standard JWT bearer tokens

---

## 6. Frontend Architecture (React 18)

### 6.1 Core Infrastructure

| File | Purpose |
|------|---------|
| `index.js` | React DOM root, StrictMode wrapper |
| `App.js` | AuthContext provider + React Router with `ProtectedRoute` wrappers. Routes gated by user role. Separate route tree for `/kiosk/*` (no auth required). 9 standard pages + kiosk app |
| `AuthContext.js` | Login state management: hits `/api/auth/login`, persists JWT to `localStorage`, provides `login()`/`logout()`/`currentUser` via React Context |
| `api.js` | Global Axios HTTP client: `baseURL` to FastAPI, automatic Bearer token injection, error interceptor, 30+ typed API functions (`kioskStart`, `kioskCapturePhoto`, `clerkAcceptLoan`, `managerRejectLoan`, etc.) |
| `index.css` | 73KB global stylesheet with design system tokens, dark mode support, component styles |

### 6.2 Standard Pages (`frontend/src/pages/`)

| Page | Size | Key Features |
|------|------|-------------|
| **LoginPage.js** | 5KB | Username/password form → AuthContext dispatch |
| **HomePage.js** | 2.9KB | Role-based routing hub — instant redirect based on user role |
| **LoanCreatePage.js** | 16KB | Clerk intake form: farmer ID + declaration ID + amount/tenure/rate/purpose. POSTs to create `LN` record |
| **FarmerDeclarationPage.js** | 14KB | Standalone farmer declaration form (amount inflation prevention) |
| **ConsentPage.js** | 37KB | Full farmer consent flow (web portal version): OTP submission, live webcam capture via PhotoCapture, GPS, bank account penny-drop initiation |
| **ClerkReviewPage.js** | 55KB | Dual-panel "System Extracted (OCR) vs Farmer Confirmed" comparison. Renders decrypted document previews and liveness photos from encrypted storage. Hard gate: clerk must verify Photo Match, Aadhaar Match, Document Integrity checkboxes. Displays structured OCR fields with per-field confidence badges. Shows low-confidence warnings. 60-second minimum review timer enforced. Supports reject with mandatory reason and category |
| **ApprovalPage.js** | 70KB | Read-only "Farmer Consent Verification" evidence block (OCR, biometrics, Aadhaar, presence, document integrity, blockchain anchor status). Dynamic Approve/Reject buttons. Manager rejection panel with 8 predefined categories + mandatory 30-char reason. Renders full approval flow stepper. Separate disbursement rejection at CBS/execution stage |
| **AuditPage.js** | 18KB | Technical dashboard: raw JSON cryptographic tokens, individual signature validations, blockchain verification status, manager rejection signature verification |
| **RegulatoryDashboard.js** | 14KB | Live charts (Recharts): approval SLAs, rejection distributions, fraud alerts, blockchain health, kiosk operations stats (sessions, Aadhaar verification rate, OCR retry rate), manager rejection stats by category |

### 6.3 Kiosk Components (`frontend/src/kiosk/` — 15 files)

| Component | Size | Purpose |
|-----------|------|---------|
| **KioskApp.js** | 3.9KB | Kiosk route orchestrator: step-based flow via `KioskContext` state machine. Maps 11 steps to components |
| **KioskContext.js** | 5.7KB | React Context + useReducer state management: `SET_SESSION`, `SET_EMPLOYEE`, `SET_FARMER`, `SET_AADHAAR_QR`, `SET_FACE_MATCH`, `SET_DOC_UPLOADED`, `SET_OCR_DATA`, `SET_OCR_CONFIRMED`, `SET_CONSENT_COMPLETE`, `SET_LOAN_DATA`, `SET_PRESENCE_DATA`, `NEXT_STEP`, `RESET`. 11-step state machine: start → terms → aadhaarQR → presence → faceMatch → aadhaar → formReady → docUpload → ocrConfirm → consent → receipt |
| **KioskStart.js** | 6.5KB | **Step 0**: Mandatory employee name + ID input fields. Calls `POST /api/kiosk/start`. Stores session token for all subsequent requests |
| **KioskTerms.js** | 5KB | **Step 1**: Scrollable T&C page with scroll completion tracking. Must scroll to bottom before accept button enables |
| **KioskAadhaarQR.js** | 6.2KB | **Step 2**: Aadhaar QR code scan (currently mock mode). Simulates QR data extraction (name, DOB, gender, address, last 4 Aadhaar digits). Dispatches `SET_AADHAAR_QR` to store identity data for later steps. Will be replaced with real html5-qrcode scanner |
| **KioskPresence.js** | 51KB | **Step 3**: The largest component. Integrates face-api.js for client-side face detection + bounding box + face centering control. Implements active liveness challenge sequence: blink → head turn → smile with progress indicators. Auto-capture mode (no manual shutter). Captures 5 frames (2 baseline + 3 challenge). Sends GPS, device fingerprint, challenge results JSON to server. Displays liveness verification results |
| **KioskFaceMatch.js** | ~5KB | **Step 4**: Face match verification comparing the Aadhaar QR photo against the live capture from Step 3. Dispatches `SET_FACE_MATCH` with match score and result |
| **KioskAadhaar.js** | 7.7KB | **Step 5**: Pre-fills Aadhaar last 4 digits from QR scan (Step 2, read-only). Farmer enters last 4 of mobile → initiate OTP → verify OTP. Dispatches `SET_FARMER` with verified name on success |
| **KioskFormInstructions.js** | 3.7KB | **Step 6**: Physical form filling instructions for the farmer — explains what fields to fill on the handwritten loan application before photographing |
| **KioskDocumentUpload.js** | 4.9KB | **Step 7**: Camera/file upload to capture photo of handwritten loan form. Runs OCR pipeline after upload, stores results via `SET_OCR_DATA` |
| **KioskOCRConfirm.js** | 10.4KB | **Step 8**: Displays OCR-extracted structured fields (all 9 fields) with per-field confidence indicators. **Uses only OCR-extracted data** — does not inherit names or other fields from Aadhaar verification steps. Farmer confirms or corrects each field. Low-confidence fields highlighted in yellow. Shows OCR source badge (google_vision/paddleocr/tesseract). Falls back to full manual entry mode if API returns `manual_required: true` |
| **KioskConsentConfirm.js** | 12.5KB | **Step 9**: Final consent flow — IVR voice call triggered. Displays 60-second countdown timer synchronized with server via 2-second polling. Shows call status (ringing/waiting), IVR method (call/SMS), farmer action needed. On `ivr_status=confirmed`, auto-completes kiosk session. Guards against double-complete with `completingRef`. Handles 401 from webhook auto-complete gracefully |
| **KioskReceipt.js** | 4.4KB | **Step 10**: Success/completion receipt with loan ID, farmer name, loan amount |
| **KioskAssistance.js** | 1.1KB | Employee assistance request component (triggers assistance mode) |
| **KioskTimeout.js** | 1KB | Session expiry display when kiosk session times out |

### 6.4 Shared Components (`frontend/src/components/`)

| Component | Size | Purpose |
|-----------|------|---------|
| **PhotoCapture.js** | 14KB | HTML5 `<video>` + `navigator.mediaDevices.getUserMedia()`. Runs client-side face-api.js models for bounding box detection. Captures sequential snapshot frames |
| **ApprovalFlow.js** | 2.9KB | Graphical stepper/progress bar: shows which manager roles have approved (green check) and which are pending (gray/yellow) |
| **LoanCard.js** | 1.2KB | Compact summary card: amount, tier, status badge. Used in list views |
| **VerificationBadge.js** | 0.8KB | Reusable pill component: Green=Verified, Red=Failed, Yellow=Pending |

---

## 7. Comprehensive Anti-Fraud Map (13 Types)

| # | Fraud Type | Technical Mechanism | Models/Services Involved |
|---|-----------|---------------------|--------------------------|
| 1 | **Benami (Proxy)** | PennyDrop service: deposits ₹1, fuzzy-matches returned name against farmer name (difflib). Blocks if similarity < threshold | `DisbursementConsent`, `penny_drop_service.py` |
| 2 | **Amount Inflation** | Immutable `FarmerDeclaration` hash created BEFORE clerk touches the application. Linked via `declaration_id` FK. SMS confirmation sent | `FarmerDeclaration`, `Loan.farmer_declared_amount` |
| 3 | **Impersonation** | 5-frame active liveness (blink + head turn + smile) + face-api.js client detection + server-side frame variance analysis + multi-face detection + GPS + device fingerprint | `KioskPresenceRecord`, `photo_verification_service.py` |
| 4 | **Internal Collusion** | Multi-signature Ed25519 requirement. Clerk cannot forge Manager; Manager cannot forge Farmer. Each signer uses unique key pair. Role-gated endpoints | `Approval`, `FarmerConsent`, `crypto_service.py`, `policy_engine.py` |
| 5 | **Database Tampering** | Loan hash recomputed from 7 params on every audit/execution. Background chain integrity checks. Blockchain anchors provide independent verification | `consent_engine.py`, `blockchain_service.py` |
| 6 | **Replay Attacks** | `UsedNonce` table records consumed nonces. Checked before consent creation. Session tokens with expiry | `nonce.py`, `kiosk_session.py` |
| 7 | **Document Forgery** | Server-side SHA-256 hash computed on raw upload bytes. 3-layer OCR with confidence scoring. Multiple engine cross-verification (Google Vision + PaddleOCR + Tesseract). Signature region hash | `LoanDocument`, `external_ocr_service.py`, `ocr_service.py`, `document_service.py` |
| 8 | **Stale Sessions** | Kiosk session tokens expire (30 min). OTPs expire in 10 minutes. Consent expires if > 30 days old | `KioskSession`, `ConsentOTPRecord`, `consent_engine.py` |
| 9 | **Rushed Execution** | Time-boxing: 5-minute minimum between consent and first approval (warning). 60-second minimum clerk review time (enforced). Timestamps are server-authoritative | `consent_engine.py`, `routes.py` |
| 10 | **Bypassed KYC** | Clerk MUST open review page (recorded timestamp) AND spend ≥60 seconds before accepting. Kiosk session completeness validated at execution time (5 sub-checks) | `Loan.clerk_review_opened_at`, `consent_engine.py` |
| 11 | **Repudiation** | Blockchain anchors (PoW chain) provide mathematical proof of state at exact time. All consent certificates include certificate hash. Override requires dual CEO+Auditor signature | `BlockchainAnchor`, `blockchain_service.py`, `OverrideRequest` |
| 12 | **Data Leakage** | All PII (photos, Aadhaar docs, OCR field data) encrypted at rest via Fernet `MASTER_KEY`. Decryption access logged with user, role, IP. Aadhaar numbers masked to XXXX-XXXX-1234 | `photo_verification_service.py`, `document_service.py`, `ocr_service.py` |
| 13 | **Unauthorized Consent** | IVR voice confirmation: farmer must independently press 1 on a Twilio phone call (or reply YES via SMS) within a strict 60-second window. Prevents clerk from consenting without farmer's knowledge. Hindi TTS (Polly.Aditi), 3-attempt retry, auto-timeout rejection | `ivr_service.py`, `Loan.ivr_status`, `routes.py` (IVR webhooks) |

---

## 8. Exhaustive File-by-File Code Manifest

### Backend Root & DB
| File | Purpose |
|------|---------|
| `backend/main.py` (96 lines) | FastAPI app entry point. CORS middleware (localhost:3000). Global exception handler with UUID request_id. Auto-creates `data/keys/`, `data/blockchain/`, `data/photos/` directories. Seeds demo users/data on startup |
| `backend/app/db/database.py` | SQLAlchemy engine (SQLite), declarative Base, `SessionLocal`, `init_db()`, `seed_users()` (bcrypt-hashed passwords), `seed_demo_data()` |
| `backend/requirements.txt` | FastAPI, SQLAlchemy, python-jose, passlib[bcrypt], cryptography, Pillow, numpy, python-dotenv, paddleocr, pytesseract, opencv-python, twilio, google-cloud-vision |
| `backend/.env` | `MASTER_KEY` (Fernet), `JWT_SECRET_KEY`, `SECRET_KEY`, `DATABASE_URL`, `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_PHONE_NUMBER`, `VOICE_WEBHOOK_BASE_URL` (ngrok/production), `GOOGLE_VISION_CREDENTIALS_PATH` |
| `backend/google_vision_credentials.json` | Google Cloud Vision API service account key (for Layer 1 OCR) |
| `backend/migrate_ocr_fields.py` | Schema migration script to add structured OCR extraction columns to `loan_documents` table |

### Backend Models (`backend/app/models/` — 14 files)
| File | Model Class | Columns | Purpose |
|------|------------|---------|---------|
| `loan.py` | `Loan` | 40+ | Central loan entity with full status lifecycle + IVR confirmation fields |
| `kiosk_presence.py` | `KioskPresenceRecord` | 22 | Physical presence + active liveness evidence |
| `kiosk_session.py` | `KioskSession` | 12 | Ephemeral 30-min kiosk session lifecycle |
| `loan_document.py` | `LoanDocument` | 28+ | Document hash + OCR extraction + farmer confirmation + OCR pipeline tracking |
| `consent_otp.py` | `ConsentOTPRecord` | 10 | OTP audit trail (never stores raw OTP) |
| `consent.py` | `FarmerConsent` | 16 | Cryptographic farmer consent proof |
| `approval.py` | `Approval` | 9 | Manager Ed25519 approval signature |
| `blockchain.py` | `BlockchainAnchor` | 6 | Links loan to PoW blockchain block |
| `disbursement.py` | `DisbursementConsent` | 11 | Penny-drop verified bank account |
| `declaration.py` | `FarmerDeclaration` | 10 | Self-declared amount (fraud prevention) |
| `notification.py` | `Notification` | 7 | SMS audit trail |
| `nonce.py` | `UsedNonce` | 3 | Replay attack prevention |
| `user.py` | `User` | 4 | RBAC user with bcrypt password |
| `override.py` | `OverrideRequest` | 9 | CEO+Auditor dual-signature emergency override |

### Backend Services (`backend/app/services/` — 19 files)
| File | Size | Key Classes/Functions |
|------|------|----------------------|
| `ocr_service.py` | 55KB (970+ lines) | `ImagePreprocessor`, `TextRecognizer`, `FieldExtractor`, `FieldValidator`, `ConfidenceScorer`, `LLMFieldExtractor`, `OCRService`, `FormRegionExtractor` |
| `document_service.py` | 23KB (522 lines) | `DocumentService`: receive_document, run_ocr (3-layer pipeline), confirm_ocr, _build_manual_required_response |
| `photo_verification_service.py` | 20KB (443 lines) | `PhotoVerificationService`: validate_image_quality, check_liveness, validate_active_liveness, check_multi_face, encrypt_and_store, decrypt_photo |
| `consent_engine.py` | 19KB (496 lines) | `ConsentEngine`: create_farmer_consent, create_manager_approval, validate_execution_eligibility (8-step) |
| `ivr_service.py` | 10.6KB | `IVRService`: _build_voice_twiml (Polly.Aditi Hindi, 3-attempt Gather), trigger_ivr_call, trigger_sms_fallback, check_ivr_timeout, is_within_window, reject_loan |
| `identity_service.py` | 9.6KB | `IdentityService`: verify_farmer_identity, send_consent_otp, verify_consent_otp, verify_device_fingerprint |
| `notification_service.py` | 8.8KB | `NotificationService`: send_loan_creation/consent/disbursement notifications, verify_notifications_sent |
| `crypto_service.py` | 8KB | `CryptoService`: Ed25519 key management, sign_data, verify_signature, Fernet encryption, generate_loan_hash, generate_consent_token |
| `blockchain_service.py` | 7.9KB | `BlockchainService`: anchor_consent, verify_chain_integrity, verify_loan_anchor, verify_full_chain |
| `kiosk_consent_service.py` | 6.6KB | `KioskConsentService`: initiate_consent_otp, verify_consent (bundles OTP + liveness + Aadhaar, triggers IVR) |
| `policy_engine.py` | 6.5KB | `PolicyEngine`: tier determination, validate_approvals, get_required/missing_approvals |
| `aadhaar_service.py` | 5.9KB | `AadhaarService`: initiate_auth, verify_auth (with ConsentOTPRecord tracking) |
| `external_ocr_service.py` | 5.6KB | `GoogleVisionOCR`: _get_client (lazy init with service account), is_available, extract_text (2 retries, 10s timeout). Raises `GoogleVisionError` on failure |
| `override_service.py` | 5.6KB | `OverrideService`: create_override_request, cosign_override |
| `kiosk_session_service.py` | 5.3KB | `KioskSessionService`: create_session, validate_session_token, update_activity, complete_session |
| `penny_drop_service.py` | 4.9KB | `PennyDropService`: verify_account_ownership (fuzzy name match via difflib) |
| `sms_service.py` | 3.3KB | `SMSService`: send_sms, send_loan_creation/declaration/disbursement_confirmation |
| `cbs_service.py` | 2.7KB | `CBSService`: validate (NPA check, eligibility scoring, ledger queries) |
| `kiosk_anchor_service.py` | 1.7KB | `KioskAnchorService`: anchor_kiosk_session (intermediate blockchain anchor) |

### Backend API (`backend/app/api/` — 3 files)
| File | Size | Purpose |
|------|------|---------|
| `routes.py` | 121KB (2910 lines) | All FastAPI routers across 15 sections: loans, consent, disbursement, declarations, approvals, manager/disbursement rejection, execution, audit, blockchain, policy, auth, identity/OTP, notifications, CBS validation, dashboard, override, consent certificate, kiosk phase (13 endpoints), IVR webhooks (4 endpoints), audit photo/document retrieval |
| `deps.py` | 3.8KB | 14 dependency injection generators: get_db, get_current_user, require_roles, get_crypto_service, get_policy_engine, get_consent_engine, get_blockchain_service, get_penny_drop_service, get_sms_service, get_identity_service, get_notification_service, get_kiosk_session_service, get_aadhaar_service, get_document_service, get_kiosk_consent_service, get_kiosk_anchor_service |
| `kiosk_deps.py` | 1.2KB | Kiosk session token validation dependency (validates X-Session-Token header) |

### Backend Schemas (`backend/app/schemas/` — 6 files)
| File | Models |
|------|--------|
| `loan_schemas.py` | LoanCreate, LoanResponse, LoanListResponse |
| `consent_schemas.py` | FarmerConsentCreate, FarmerConsentResponse |
| `approval_schemas.py` | ApprovalCreate, ApprovalResponse |
| `disbursement_schemas.py` | DisbursementConsentCreate, DisbursementConsentResponse |
| `declaration_schemas.py` | FarmerDeclarationCreate, FarmerDeclarationResponse |
| `auth_schemas.py` | LoginRequest, LoginResponse |

### Backend Utilities
| File | Purpose |
|------|---------|
| `backend/app/utils/helpers.py` | Shared helper functions |

### Frontend Structure (`frontend/src/` — 5 core files + 3 directories)
| File | Size | Purpose |
|------|------|---------|
| `App.js` | 5.4KB | React Router with ProtectedRoute wrappers, role-based routing, separate kiosk route tree |
| `AuthContext.js` | 3.1KB | Login/logout state, JWT storage in localStorage, role-based redirects |
| `api.js` | 8.3KB | Axios client with Bearer token injection, 30+ typed API functions for all endpoints |
| `index.js` | 273B | React DOM root |
| `index.css` | 73KB | Full design system: dark mode, glassmorphism, animations, responsive layouts |

### Frontend Pages (`frontend/src/pages/` — 9 files)
| File | Size | Purpose |
|------|------|---------|
| `ApprovalPage.js` | 70KB | Manager approval + rejection with full evidence display |
| `ClerkReviewPage.js` | 55KB | Dual-pane review with structured OCR comparison, decrypted documents/photos, 60s review timer |
| `ConsentPage.js` | 37KB | Web portal farmer consent: OTP + webcam + GPS + penny-drop |
| `AuditPage.js` | 18KB | Technical audit dashboard with cryptographic verification |
| `LoanCreatePage.js` | 16KB | Clerk loan intake form |
| `FarmerDeclarationPage.js` | 14KB | Farmer self-declared amount form |
| `RegulatoryDashboard.js` | 14KB | Live charts: approval SLAs, rejections, fraud alerts, kiosk stats |
| `LoginPage.js` | 5KB | Authentication form |
| `HomePage.js` | 2.9KB | Role-based routing hub |

### Frontend Kiosk (`frontend/src/kiosk/` — 15 files)
| File | Size | Purpose |
|------|------|---------|
| `KioskPresence.js` | 51KB | Face detection + active liveness challenges + auto-capture |
| `KioskConsentConfirm.js` | 12.5KB | Final consent + IVR voice call + completion + blockchain anchoring |
| `KioskOCRConfirm.js` | 10.4KB | 9-field OCR confirmation with confidence indicators. Uses only OCR-extracted data (not Aadhaar) |
| `KioskAadhaar.js` | 7.7KB | Aadhaar last 4 (pre-filled from QR) + mobile last 4 + OTP verification |
| `KioskAadhaarQR.js` | 6.2KB | Aadhaar QR code scan (mock mode) — extracts identity from QR |
| `KioskStart.js` | 6.5KB | Mandatory employee + session creation |
| `KioskContext.js` | 5.7KB | Kiosk state machine (useReducer) with 11 steps |
| `KioskFaceMatch.js` | ~5KB | Aadhaar photo vs live capture face match |
| `KioskTerms.js` | 5KB | T&C with scroll tracking |
| `KioskDocumentUpload.js` | 4.9KB | Camera/file upload for loan form photo + OCR trigger |
| `KioskReceipt.js` | 4.4KB | Completion receipt with loan details |
| `KioskApp.js` | 3.9KB | Step-based route orchestrator (11 steps) |
| `KioskFormInstructions.js` | 3.7KB | Physical form filling instructions |
| `KioskAssistance.js` | 1.1KB | Employee assistance request |
| `KioskTimeout.js` | 1KB | Session expiry display |

### Frontend Components (`frontend/src/components/` — 4 files)
| File | Size | Purpose |
|------|------|---------|
| `PhotoCapture.js` | 14KB | HTML5 video + face-api.js bounding box + sequential frame capture |
| `ApprovalFlow.js` | 2.9KB | Graphical approval stepper (green/gray/yellow status per role) |
| `LoanCard.js` | 1.2KB | Compact loan summary card for lists |
| `VerificationBadge.js` | 0.8KB | Reusable status pill (Verified/Failed/Pending) |

---

## 9. Data Directories

| Directory | Contents |
|-----------|----------|
| `data/keys/` | Ed25519 key pairs (`.pem` files), optionally Fernet-encrypted at rest |
| `data/photos/` | Fernet-encrypted photo files (`{loan_id}.enc`) — length-prefixed multi-frame format |
| `data/blockchain/` | `blockchain_data.json` — local PoW blockchain |
| `blockchain/` | Alternative blockchain storage directory |
| `backend/cge_system.db` | SQLite database (15 tables, ~300KB in development) |

---

> *End of Implementation Reference. All code changes and future enhancements should align with the architectural boundaries defined above.*
