"""
Database configuration for SQLAlchemy.
Uses SQLite by default; supports PostgreSQL via DATABASE_URL.
Includes WAL mode for SQLite concurrency, bcrypt password hashing,
and comprehensive demo data seeding with kiosk session records.
"""

import os
import json
import time
import hashlib
import uuid
from datetime import datetime, timezone, timedelta
from sqlalchemy import create_engine, event
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{os.path.join(BASE_DIR, '..', '..', 'cge_system.db')}")

if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

    # §2.4 — WAL mode for SQLite concurrency
    @event.listens_for(engine, "connect")
    def _set_sqlite_wal(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()
else:
    engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """Yield a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables. Import models so they are registered on Base."""
    from app.models.loan import Loan
    from app.models.consent import FarmerConsent
    from app.models.approval import Approval
    from app.models.blockchain import BlockchainAnchor
    from app.models.user import User
    from app.models.disbursement import DisbursementConsent
    from app.models.declaration import FarmerDeclaration
    from app.models.notification import Notification
    from app.models.override import OverrideRequest
    from app.models.nonce import UsedNonce
    from app.models.kiosk_session import KioskSession
    from app.models.kiosk_presence import KioskPresenceRecord
    from app.models.loan_document import LoanDocument
    from app.models.consent_otp import ConsentOTPRecord

    Base.metadata.create_all(bind=engine)

    # Lightweight migration: add new columns to existing tables
    _columns_to_add = [
        ("loans", "cbs_validated_at", "DATETIME"),
        ("loans", "kiosk_session_id", "VARCHAR(64)"),
        ("loans", "aadhaar_verified_name", "VARCHAR(255)"),
        ("loans", "document_hash", "VARCHAR(64)"),
        ("loans", "kiosk_phase_anchor_hash", "VARCHAR(64)"),
        ("loans", "kiosk_completed_at", "DATETIME"),
        ("loans", "assistance_session", "BOOLEAN DEFAULT 0"),
        ("loans", "clerk_reviewed_by", "VARCHAR(100)"),
        ("loans", "clerk_accepted_at", "DATETIME"),
        ("loans", "clerk_rejected_at", "DATETIME"),
        ("loans", "rejection_reason", "TEXT"),
        ("loans", "rejection_category", "VARCHAR(100)"),
        ("loans", "assisting_employee_name", "VARCHAR(255)"),
        ("loans", "assisting_employee_id", "VARCHAR(100)"),
        ("kiosk_presence_records", "device_fingerprint_hash", "VARCHAR(64)"),
        ("kiosk_presence_records", "assisting_employee_name", "VARCHAR(255)"),
        ("kiosk_presence_records", "assisting_employee_id", "VARCHAR(100)"),
        ("loans", "clerk_review_opened_at", "DATETIME"),
        ("kiosk_sessions", "assisting_employee_name", "VARCHAR(255)"),
        ("kiosk_sessions", "assisting_employee_id", "VARCHAR(100)"),
    ]
    for table, column, col_type in _columns_to_add:
        try:
            with engine.connect() as conn:
                conn.execute(__import__("sqlalchemy").text(
                    f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"
                ))
                conn.commit()
        except Exception:
            pass  # Column already exists — safe to ignore


def seed_users():
    """Insert predefined demo users with bcrypt password hashing.
    Farmer users removed — farmers use the sessionless kiosk flow.
    """
    from passlib.hash import bcrypt as bcrypt_hash
    from app.models.user import User

    db = SessionLocal()
    try:
        def _hash(pw: str) -> str:
            return bcrypt_hash.using(rounds=12).hash(pw)

        # Password map for re-hashing stale SHA-256 hashes
        _passwords = {
            "CLERK001": "clerk123",
            "EMP101": "mgr123", "EMP201": "mgr123", "EMP301": "mgr123",
            "EMP401": "mgr123", "AUD001": "audit123",
        }

        existing_count = db.query(User).count()
        if existing_count > 0:
            # Check if existing hashes are stale (SHA-256 = 64-char hex, bcrypt starts with $2b$)
            first_user = db.query(User).first()
            if first_user and first_user.password_hash and not first_user.password_hash.startswith("$2b$"):
                print("⚠ Detected stale SHA-256 password hashes — upgrading to bcrypt...")
                for user in db.query(User).all():
                    plain = _passwords.get(user.user_id)
                    if plain:
                        user.password_hash = _hash(plain)
                db.commit()
                print(f"✅ Upgraded {existing_count} users to bcrypt hashes")
            return  # already seeded (and now fixed)

        demo_users = [
            User(user_id="CLERK001", name="Anil Kumar",    role="clerk",            password_hash=_hash("clerk123")),
            User(user_id="EMP101",   name="Suresh Kumar",   role="branch_manager",   password_hash=_hash("mgr123")),
            User(user_id="EMP201",   name="Priya Sharma",   role="credit_manager",   password_hash=_hash("mgr123")),
            User(user_id="EMP301",   name="Rajesh Patel",   role="ceo",              password_hash=_hash("mgr123")),
            User(user_id="EMP401",   name="Anita Desai",    role="board_member",     password_hash=_hash("mgr123")),
            User(user_id="AUD001",   name="Vikram Singh",   role="auditor",          password_hash=_hash("audit123")),
        ]
        db.add_all(demo_users)
        db.commit()
        print(f"✅ Seeded {len(demo_users)} demo users (bcrypt hashed, no farmer accounts)")
    finally:
        db.close()


def _compute_loan_hash(params: dict) -> str:
    """Compute SHA-256 hash of canonical JSON loan parameters."""
    canonical = json.dumps(params, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def seed_demo_data():
    """Seed 25 realistic demo loans with completed kiosk session records."""
    from app.models.loan import Loan
    from app.models.consent import FarmerConsent
    from app.models.approval import Approval
    from app.models.blockchain import BlockchainAnchor
    from app.models.declaration import FarmerDeclaration
    from app.models.disbursement import DisbursementConsent
    from app.models.notification import Notification
    from app.models.kiosk_session import KioskSession
    from app.models.kiosk_presence import KioskPresenceRecord
    from app.models.loan_document import LoanDocument
    from app.models.consent_otp import ConsentOTPRecord

    db = SessionLocal()
    try:
        if db.query(Loan).count() > 0:
            return  # already seeded

        now = datetime.now(timezone.utc)

        # Farmer names with Aadhaar last-four for kiosk verification
        farmers = [
            ("Ramesh Sharma",   "9876543210", "Vidisha",      "4521"),
            ("Sita Devi",       "9876543211", "Dhar",         "7832"),
            ("Gopal Yadav",     "9876543212", "Sehore",       "3156"),
            ("Lakshmi Bai",     "9876543213", "Raisen",       "6294"),
            ("Mohan Patel",     "9876543214", "Hoshangabad",  "8471"),
            ("Kamla Devi",      "9876543215", "Vidisha",      "1923"),
            ("Raju Singh",      "9876543216", "Dhar",         "5047"),
            ("Sunita Kumari",   "9876543217", "Sehore",       "2385"),
            ("Harish Verma",    "9876543218", "Raisen",       "9160"),
            ("Meena Sharma",    "9876543219", "Hoshangabad",  "7534"),
            ("Bhola Nath",      "9876543220", "Vidisha",      "4289"),
            ("Durga Devi",      "9876543221", "Dhar",         "6107"),
            ("Pratap Singh",    "9876543222", "Sehore",       "8653"),
            ("Anita Bai",       "9876543223", "Raisen",       "3948"),
            ("Dinesh Kumar",    "9876543224", "Hoshangabad",  "7216"),
            ("Pushpa Devi",     "9876543225", "Vidisha",      "5839"),
            ("Kishan Lal",      "9876543226", "Dhar",         "1472"),
            ("Savitri Devi",    "9876543227", "Sehore",       "9384"),
            ("Vijay Sharma",    "9876543228", "Raisen",       "2761"),
            ("Radha Bai",       "9876543229", "Hoshangabad",  "6095"),
            ("Ajay Patel",      "9876543230", "Vidisha",      "4521"),
            ("Geeta Devi",      "9876543231", "Dhar",         "7832"),
            ("Mahesh Yadav",    "9876543232", "Sehore",       "3156"),
            ("Parvati Devi",    "9876543233", "Raisen",       "6294"),
            ("Suresh Verma",    "9876543234", "Hoshangabad",  "8471"),
        ]

        purposes = [
            "Kharif crop inputs", "Rabi crop seeds", "Irrigation equipment",
            "Farm machinery repair", "Fertilizer purchase", "Warehouse storage",
            "Crop insurance premium", "Agricultural tools", "Livestock feed",
            "Post-harvest processing"
        ]

        # Loan amounts by tier
        tier1_amounts = [75000.0, 85000.0, 90000.0, 95000.0, 80000.0]
        tier2_amounts = [350000.0, 450000.0, 400000.0, 500000.0]
        tier3_amounts = [1500000.0, 1200000.0, 1000000.0]

        # Status distribution: 3 pending_clerk_review, 2 clerk_rejected,
        # 4 pending_approvals, 3 cbs_validated, 3 ready_for_execution, 5 executed, 5 anchored
        statuses = (
            ["pending_clerk_review"] * 3 +
            ["clerk_rejected"] * 2 +
            ["pending_approvals"] * 4 +
            ["cbs_validated"] * 3 +
            ["ready_for_execution"] * 3 +
            ["executed"] * 5 +
            ["anchored"] * 5
        )

        # Assisted session indices (employee was present)
        assisted_indices = {0, 1, 5}
        assisted_employees = [
            ("Anil Kumar", "CLERK001"),
            ("Anil Kumar", "CLERK001"),
            ("Suresh Kumar", "EMP101"),
        ]

        amounts = (
            tier1_amounts +  # 5 loans
            [tier2_amounts[0], tier2_amounts[1], tier1_amounts[0], tier1_amounts[1]] +  # 4 loans
            [tier1_amounts[2], tier2_amounts[2], tier1_amounts[3]] +  # 3 loans
            [tier1_amounts[4], tier2_amounts[3], tier1_amounts[0]] +  # 3 loans
            tier1_amounts +  # 5 loans
            [tier1_amounts[0], tier1_amounts[1], tier2_amounts[0], tier1_amounts[2], tier1_amounts[3]]  # 5 loans
        )

        block_number = 0
        prev_hash = "0" * 64

        for i in range(25):
            loan_id = f"LN{1700000000000 + i * 1000}"
            farmer_name, mobile, district, aadhaar_last4 = farmers[i]
            farmer_id = f"KIOSK-{aadhaar_last4}"
            amount = amounts[i]
            status = statuses[i]
            purpose = purposes[i % len(purposes)]
            tenure = 12 if amount < 200000 else (24 if amount < 1000000 else 36)
            interest_rate = 7.0 if amount < 200000 else (8.5 if amount < 1000000 else 9.5)

            # Determine tier
            if amount <= 100000:
                tier = "tier_1"
            elif amount <= 500000:
                tier = "tier_2"
            elif amount <= 2500000:
                tier = "tier_3"
            else:
                tier = "tier_4"

            # Compute loan hash
            hash_params = {
                "loan_id": loan_id,
                "farmer_id": farmer_id,
                "farmer_name": farmer_name,
                "amount": amount,
                "tenure_months": tenure,
                "interest_rate": interest_rate,
                "purpose": purpose,
            }
            loan_hash = _compute_loan_hash(hash_params)

            created_at = now - timedelta(days=30 - i)
            session_id = str(uuid.uuid4())
            kiosk_anchor_hash = hashlib.sha256(f"kiosk_anchor_{loan_id}".encode()).hexdigest()

            # Fraud flags for 2 anchored loans
            amount_diff_reason = None
            if status == "anchored" and i == 23:
                amount_diff_reason = "Clerk entered higher amount than farmer declared"

            # Clerk rejection data
            rejection_reason = None
            rejection_category = None
            clerk_rejected_at_ts = None
            clerk_reviewed_by = None
            clerk_accepted_at_ts = None
            if status == "clerk_rejected":
                rejection_reason = "Uploaded document is blurry, signature not visible. Please re-submit with clearer scan."
                rejection_category = "Incomplete Documentation"
                clerk_rejected_at_ts = created_at + timedelta(hours=1)
                clerk_reviewed_by = "CLERK001"
            elif status in ("pending_approvals", "cbs_validated", "ready_for_execution", "executed", "anchored"):
                clerk_reviewed_by = "CLERK001"
                clerk_accepted_at_ts = created_at + timedelta(minutes=45)

            # Assisted session data
            assist_name = None
            assist_id = None
            if i in assisted_indices:
                idx = list(assisted_indices).index(i)
                assist_name, assist_id = assisted_employees[idx]

            metadata = None
            cbs_validated_at = None
            if status in ("cbs_validated", "ready_for_execution", "executed", "anchored"):
                cbs_validated_at = created_at + timedelta(hours=2)
                metadata = json.dumps({
                    "CBS_REF_ID": f"CBS{1700000000 + i}",
                    "ELIGIBILITY_STATUS": "ELIGIBLE",
                    "NPA_FLAG": "N",
                })

            doc_hash = hashlib.sha256(f"doc_{loan_id}".encode()).hexdigest()

            loan = Loan(
                loan_id=loan_id,
                farmer_id=farmer_id,
                farmer_name=farmer_name,
                farmer_mobile=mobile,
                amount=amount,
                tenure_months=tenure,
                interest_rate=interest_rate,
                purpose=purpose,
                loan_hash=loan_hash,
                status=status,
                approval_tier=tier,
                created_by="CLERK001",
                created_at=created_at,
                updated_at=created_at + timedelta(hours=1),
                metadata_json=metadata,
                cbs_validated_at=cbs_validated_at,
                amount_difference_reason=amount_diff_reason,
                kiosk_session_id=session_id,
                aadhaar_verified_name=farmer_name,
                document_hash=doc_hash,
                kiosk_phase_anchor_hash=kiosk_anchor_hash,
                kiosk_completed_at=created_at + timedelta(minutes=15),
                clerk_reviewed_by=clerk_reviewed_by,
                clerk_accepted_at=clerk_accepted_at_ts,
                clerk_rejected_at=clerk_rejected_at_ts,
                rejection_reason=rejection_reason,
                rejection_category=rejection_category,
                assisting_employee_name=assist_name,
                assisting_employee_id=assist_id,
                assistance_session=i in assisted_indices,
            )
            db.add(loan)
            db.flush()

            # Create completed kiosk session for all loans
            kiosk_session = KioskSession(
                session_id=session_id,
                loan_id=loan_id,
                session_token="",  # cleared after completion
                session_token_expires_at=created_at + timedelta(minutes=30),
                session_status="completed",
                session_started_at=created_at,
                session_completed_at=created_at + timedelta(minutes=15),
                last_activity_at=created_at + timedelta(minutes=15),
                ip_address="127.0.0.1",
            )
            db.add(kiosk_session)

            # Create presence record
            presence = KioskPresenceRecord(
                loan_id=loan_id,
                gps_latitude=23.2599 + (i * 0.01),
                gps_longitude=77.4126 + (i * 0.01),
                gps_captured_at=created_at + timedelta(minutes=2),
                photo_hash=hashlib.sha256(f"photo_{loan_id}".encode()).hexdigest(),
                photo_encrypted_storage_path=f"data/photos/{loan_id}.enc",
                aadhaar_last_four=aadhaar_last4,
                aadhaar_hash=hashlib.sha256(f"1234-5678-{aadhaar_last4}".encode()).hexdigest(),
                aadhaar_verified_name=farmer_name,
                aadhaar_otp_verified=True,
                aadhaar_verified_at=created_at + timedelta(minutes=5),
                device_fingerprint_hash=hashlib.sha256(f"device_{loan_id}".encode()).hexdigest(),
                terms_accepted_at=created_at + timedelta(minutes=1),
                terms_scroll_completed=True,
                assisting_employee_name=assist_name,
                assisting_employee_id=assist_id,
            )
            db.add(presence)

            # Create loan document record
            loan_doc = LoanDocument(
                loan_id=loan_id,
                document_hash=doc_hash,
                signature_region_hash=hashlib.sha256(f"sig_{loan_id}".encode()).hexdigest(),
                encrypted_document_path=f"data/documents/{loan_id}.enc",
                ocr_extracted_amount=amount,
                ocr_extracted_purpose=purpose,
                ocr_extracted_farmer_name=farmer_name,
                ocr_confidence_score=0.92,
                farmer_confirmed_amount=amount,
                farmer_confirmed_purpose=purpose,
                ocr_confirmation_attempts=1,
                ocr_confirmed_at=created_at + timedelta(minutes=10),
                document_uploaded_at=created_at + timedelta(minutes=7),
            )
            db.add(loan_doc)

            # Create consent OTP records (both aadhaar_auth and loan_consent)
            aadhaar_otp_ref = str(uuid.uuid4())
            consent_otp_ref = str(uuid.uuid4())
            db.add(ConsentOTPRecord(
                loan_id=loan_id,
                otp_type="aadhaar_auth",
                otp_hash=hashlib.sha256(b"123456").hexdigest(),
                otp_reference_id=aadhaar_otp_ref,
                mobile_last_four=mobile[-4:],
                issued_at=created_at + timedelta(minutes=4),
                expires_at=created_at + timedelta(minutes=14),
                verified_at=created_at + timedelta(minutes=5),
                used=True,
                attempt_count=1,
            ))
            db.add(ConsentOTPRecord(
                loan_id=loan_id,
                otp_type="loan_consent",
                otp_hash=hashlib.sha256(b"654321").hexdigest(),
                otp_reference_id=consent_otp_ref,
                mobile_last_four=mobile[-4:],
                issued_at=created_at + timedelta(minutes=12),
                expires_at=created_at + timedelta(minutes=22),
                verified_at=created_at + timedelta(minutes=13),
                used=True,
                attempt_count=1,
            ))

            # Add consent for all loans (kiosk flow generates consent)
            consent = FarmerConsent(
                loan_id=loan_id,
                loan_hash=loan_hash,
                farmer_signature=f"demo_sig_{loan_id}",
                consent_method="kiosk_aadhaar_otp",
                otp_verified="1234",
                ip_address="127.0.0.1",
                consented_at=created_at + timedelta(minutes=13),
                bank_kyc_verified=True,
                live_photo_hash=hashlib.sha256(f"photo_{loan_id}".encode()).hexdigest(),
                gps_latitude=23.2599 + (i * 0.01),
                gps_longitude=77.4126 + (i * 0.01),
            )
            db.add(consent)

            # Add notifications
            for ntype in ["loan_creation", "consent_confirmation"]:
                notif = Notification(
                    loan_id=loan_id,
                    notification_type=ntype,
                    recipient_mobile=mobile,
                    sms_content=f"[Demo] {ntype} for {loan_id}",
                    delivery_status="sent",
                )
                db.add(notif)

            # Add approvals for loans past pending_clerk_review
            if status in ("pending_approvals", "cbs_validated", "ready_for_execution", "executed", "anchored"):
                approval = Approval(
                    loan_id=loan_id,
                    approver_id="EMP101",
                    approver_name="Suresh Kumar",
                    approver_role="branch_manager",
                    loan_hash=loan_hash,
                    approver_signature=f"demo_mgr_sig_{loan_id}",
                    comments="Approved after review",
                    approved_at=created_at + timedelta(hours=1),
                )
                db.add(approval)

                if tier in ("tier_2", "tier_3", "tier_4"):
                    approval2 = Approval(
                        loan_id=loan_id,
                        approver_id="EMP201",
                        approver_name="Priya Sharma",
                        approver_role="credit_manager",
                        loan_hash=loan_hash,
                        approver_signature=f"demo_cm_sig_{loan_id}",
                        approved_at=created_at + timedelta(hours=1, minutes=30),
                    )
                    db.add(approval2)

            # Add disbursement consent for executed/anchored loans
            if status in ("executed", "anchored"):
                disb_hash = _compute_loan_hash({
                    "loan_id": loan_id,
                    "account_number": f"1234567890{i:02d}",
                    "ifsc_code": "SVCB0000001",
                    "account_holder_name": farmer_name,
                })
                penny_matched = not (status == "anchored" and i == 24)
                disb = DisbursementConsent(
                    loan_id=loan_id,
                    account_number=f"1234567890{i:02d}",
                    account_holder_name=farmer_name,
                    ifsc_code="SVCB0000001",
                    penny_drop_verified=True,
                    penny_drop_name_matched=penny_matched,
                    penny_drop_response=json.dumps({"verified": True, "name_matched": penny_matched}),
                    disbursement_hash=disb_hash,
                )
                db.add(disb)
                db.add(Notification(
                    loan_id=loan_id,
                    notification_type="disbursement",
                    recipient_mobile=mobile,
                    sms_content=f"[Demo] disbursement for {loan_id}",
                    delivery_status="sent",
                ))

            # Add blockchain anchors for anchored loans
            if status == "anchored":
                block_number += 1
                consent_hash = hashlib.sha256(
                    f"consent_token_{loan_id}".encode()
                ).hexdigest()
                anchored_at = created_at + timedelta(hours=3)
                block_hash = hashlib.sha256(
                    (prev_hash + consent_hash + anchored_at.isoformat()).encode()
                ).hexdigest()
                anchor = BlockchainAnchor(
                    loan_id=loan_id,
                    consent_hash=consent_hash,
                    block_number=block_number,
                    transaction_hash=block_hash,
                    anchored_at=anchored_at,
                    blockchain_response=json.dumps({
                        "block_number": block_number,
                        "hash": block_hash,
                        "prev_hash": prev_hash,
                        "consent_hash": consent_hash,
                    }),
                )
                db.add(anchor)
                prev_hash = block_hash

        db.commit()
        print(f"✅ Seeded 25 demo loans with kiosk session records and realistic lifecycle data")
    except Exception as e:
        db.rollback()
        print(f"⚠ Demo data seeding failed: {e}")
    finally:
        db.close()
