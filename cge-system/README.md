# 🏦 Cryptographic Governance Engine (CGE)

## Zero-Trust Loan Execution Architecture for Cooperative Banks

> **Problem**: ₹60,000+ crore in cooperative bank frauds (RBI 2019–2024) from insider manipulation — ghost loans created in farmers' names, inflated amounts, and money diverted to third-party accounts.

> **Solution**: A cryptographic execution engine where no loan can be disbursed without mathematically verified consent from every authorized party. Each parameter is hash-signed at capture time, creating a tamper-proof chain where any modification is instantly detected.

---

## 🔐 Core Security Architecture

```
Loan Created → Hash Generated → Farmer Consent (OTP + KYC + Biometric)
                                        ↓
                              Manager Approvals (N-of-M signatures)
                                        ↓
                              Execution Validation Engine
                                  ├── Hash integrity check
                                  ├── All signatures verified
                                  ├── SMS notifications confirmed
                                  ├── Time-based validation
                                  ├── Penny-drop account verification
                                  └── Policy compliance check
                                        ↓
                              Blockchain Anchor (immutable proof)
```

### Fraud Prevention Capabilities

| Fraud Type | Prevention Mechanism |
|---|---|
| **Ghost Loans** | OTP-verified farmer consent + live photo + biometric |
| **Amount Inflation** | Farmer self-declaration vs clerk amount comparison |
| **Benami Accounts** | Penny-drop verification of disbursement account |
| **Parameter Tampering** | SHA-256 hash binding – any change invalidates chain |
| **Forged Approvals** | Ed25519 per-party digital signatures |
| **Missing Consent** | SMS notification audit trail – execution blocked without notifications |

---

## 🛠 Technology Stack

| Component | Technology | Purpose |
|---|---|---|
| Backend | Python + FastAPI | REST API + business logic |
| Signing | Ed25519 (PyNaCl) | Fast, secure digital signatures |
| Hashing | SHA-256 | Tamper-proof parameter binding |
| Database | SQLite (dev) / PostgreSQL (prod) | Persistent storage |
| Blockchain | Private chain (JSON-based) | Immutable audit trail |
| Frontend | React.js | Clerk/Manager UI |
| Identity | Bank KYC + OTP | Farmer identity verification |
| Notifications | SMS Gateway (mock) | Independent farmer alert system |
| IVR | Twilio (dev) / Asterisk (prod) | Voice-based consent confirmation |

> **IVR Deployment Note**: MVP uses Twilio IVR for voice-based consent confirmation. Production deployment uses Asterisk self-hosted IVR so no call data leaves the bank's internal network, addressing RBI data localization requirements.

---

## 📁 Project Structure

```
cge-system/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── routes.py          # All API endpoints
│   │   │   └── deps.py            # Dependency injection
│   │   ├── models/
│   │   │   ├── loan.py            # Loan model
│   │   │   ├── consent.py         # Farmer consent (KYC + OTP + biometric)
│   │   │   ├── approval.py        # Manager approval signatures
│   │   │   ├── disbursement.py    # Disbursement consent (penny-drop)
│   │   │   ├── declaration.py     # Farmer self-declaration
│   │   │   ├── notification.py    # SMS notification audit trail
│   │   │   └── blockchain.py      # Blockchain anchor records
│   │   ├── services/
│   │   │   ├── consent_engine.py  # Core validation engine
│   │   │   ├── crypto_service.py  # SHA-256 + Ed25519 operations
│   │   │   ├── identity_service.py    # Bank KYC + OTP verification
│   │   │   ├── notification_service.py # SMS notifications + audit
│   │   │   ├── blockchain_service.py  # Private blockchain
│   │   │   ├── penny_drop_service.py  # Account verification
│   │   │   ├── sms_service.py     # SMS gateway integration
│   │   │   └── policy_engine.py   # Tier-based approval rules
│   │   └── schemas/               # Pydantic request/response schemas
│   └── tests/
│       ├── test_workflow.py       # End-to-end integration tests
│       ├── test_fraud_scenarios.py # Fraud detection tests
│       ├── test_crypto.py         # Cryptographic operation tests
│       └── test_policy.py         # Policy engine tests
├── frontend/
│   └── src/
│       ├── pages/
│       │   ├── ConsentPage.js     # Bilingual farmer consent (clerk-operated)
│       │   ├── LoanCreatePage.js  # Loan creation with SMS preview
│       │   ├── ApprovalPage.js    # Manager approval with verification grid
│       │   ├── AuditPage.js       # Loan audit verification
│       │   └── LoginPage.js       # Role-based authentication
│       └── api.js                 # API client
└── IMPLEMENTATION_NOTES.md        # Design rationale document
```

---

## 🔧 Prerequisites

### OCR Engine Setup (for document extraction)

1. **Tesseract OCR** — Required for text extraction from handwritten forms:
   - Download from https://github.com/UB-Mannheim/tesseract/wiki (Windows 64-bit installer)
   - During install, expand **Additional Language Data** and check **Hindi**
   - Verify installation: `tesseract --version`
   - `pip install pytesseract` (already in requirements.txt)
   - Set path in `backend/.env`: `TESSERACT_PATH=C:\Program Files\Tesseract-OCR\tesseract.exe`

2. **Ollama + LLaVA 7B** — Optional, enhances handwriting recognition with vision AI:
   - Download from https://ollama.com (Windows installer)
   - Pull the vision model: `ollama pull llava:7b` (~4GB download, runs offline after)
   - Start Ollama: `ollama serve`
   - The backend automatically detects Ollama on startup and enables/disables vision OCR accordingly

3. **PaddleOCR** — Included in `requirements.txt` (pinned to stable versions):
   - `paddlepaddle==2.6.1` + `paddleocr==2.7.3`
   - If you encounter version issues, run:
     ```bash
     pip uninstall paddleocr paddlepaddle -y
     pip install paddlepaddle==2.6.1
     pip install paddleocr==2.7.3
     ```

---

## 🚀 Quick Start

```bash
# Option 1: Using convenience script (starts Ollama + Backend)
start_backend.bat

# Option 2: Manual startup
# Backend
cd backend
pip install -r requirements.txt
ollama serve           # Optional: start Ollama in separate terminal
uvicorn main:app --reload --port 8000

# Frontend
cd frontend
npm install
npm start
```

---

## 🧪 Testing

```bash
cd backend
python -m pytest tests/ -v
```

---

## 📖 License

Academic project – CSIC Cybersecurity Innovation Challenge.
