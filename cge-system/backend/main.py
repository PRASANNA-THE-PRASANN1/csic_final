"""
CGE System FastAPI Application Entry Point.
Includes global error handling and MASTER_KEY startup check.
"""

import os
import sys
import uuid
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.db.database import init_db, seed_users, seed_demo_data
from app.api.routes import router


# §2.3 — Startup check for MASTER_KEY
MASTER_KEY = os.getenv("MASTER_KEY")
if not MASTER_KEY:
    from dotenv import load_dotenv
    load_dotenv()
    MASTER_KEY = os.getenv("MASTER_KEY")
    if not MASTER_KEY:
        print("⚠ WARNING: MASTER_KEY not set. Private keys will NOT be encrypted at rest.")


app = FastAPI(
    title="CGE System API",
    description="Cryptographic Consent & Governance Engine – India's first "
                "cryptographically-enforced rural credit consent infrastructure. "
                "Loan processing with cryptographic consent, multi-level approvals, "
                "policy enforcement, and blockchain audit trail.",
    version="1.0.0",
)

allowed_origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]
_frontend_url = os.getenv("FRONTEND_URL", "")
if _frontend_url:
    allowed_origins.append(_frontend_url)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# §2.5 — Global error handler: no raw tracebacks exposed
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch all unhandled exceptions and return structured JSON.
    Never expose Python tracebacks or internal file paths in API responses."""
    request_id = str(uuid.uuid4())
    # Log the actual error for debugging
    import logging
    import traceback
    logging.getLogger("cge").error(f"[{request_id}] Unhandled error: {exc}", exc_info=True)
    print(f"[ERROR {request_id}] {type(exc).__name__}: {exc}")
    traceback.print_exc()
    return JSONResponse(
        status_code=500,
        content={
            "error_code": "INTERNAL_ERROR",
            "message": "An unexpected error occurred",
            "request_id": request_id,
        },
    )


app.include_router(router, prefix="/api")

_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))

@app.on_event("startup")
def on_startup():
    """Initialize the database and data directories on startup."""
    os.makedirs(os.path.join(_BACKEND_DIR, "data", "keys"), exist_ok=True)
    os.makedirs(os.path.join(_BACKEND_DIR, "data", "blockchain"), exist_ok=True)
    os.makedirs(os.path.join(_BACKEND_DIR, "data", "photos"), exist_ok=True)
    os.makedirs(os.path.join(_BACKEND_DIR, "data", "documents"), exist_ok=True)
    init_db()
    seed_users()
    seed_demo_data()

    # Fix 8: Ollama startup check (non-blocking, purely informational)
    ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
    try:
        import urllib.request
        req = urllib.request.Request(f"{ollama_url}/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            if resp.status == 200:
                import json
                data = json.loads(resp.read().decode())
                models = [m.get("name", "") for m in data.get("models", [])]
                ollama_model = os.getenv("OLLAMA_MODEL", "llava:7b")
                if any(ollama_model.split(":")[0] in name for name in models):
                    print(f"✓ Ollama available — {ollama_model} vision OCR enabled")
                else:
                    print(f"⚠ Ollama running but {ollama_model} not found. "
                          f"Pull it with: ollama pull {ollama_model}")
                    print(f"  Available models: {', '.join(models) if models else 'none'}")
    except Exception:
        print("⚠ Ollama not available — LLaVA vision fallback disabled. "
              "OCR will use PaddleOCR and Tesseract only.")


@app.get("/", tags=["Health"])
def root():
    return {
        "service": "CGE System API",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
    }


@app.get("/api/health", tags=["Health"])
def health():
    return {"status": "healthy"}
