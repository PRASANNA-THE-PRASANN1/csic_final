"""
ExternalOCRService — Google Cloud Vision API wrapper for document text detection.

Layer 1 of the 3-layer OCR pipeline:
  1. Google Cloud Vision (this file) — primary, cloud-based
  2. Local PaddleOCR + Tesseract (ocr_service.py) — offline fallback
  3. Manual entry signal — final fallback

Features:
  - Max 2 retries with 10-second timeout per attempt
  - Raises GoogleVisionError on ANY failure so caller falls through to Layer 2
  - Does NOT log raw OCR text (privacy/security requirement)
"""

import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class GoogleVisionError(Exception):
    """Raised when Google Cloud Vision API call fails for any reason."""
    pass


class GoogleVisionOCR:
    """Google Cloud Vision document_text_detection wrapper."""

    MAX_RETRIES = 2
    TIMEOUT = 10  # seconds per attempt

    _client = None
    _available = None

    @classmethod
    def _get_client(cls):
        """Lazy-load the Vision API client with service account credentials."""
        if cls._client is not None:
            return cls._client

        try:
            from google.cloud import vision
            from google.oauth2 import service_account

            creds_path = os.getenv("GOOGLE_VISION_CREDENTIALS_PATH", "")
            if not creds_path:
                # Try default location relative to backend root
                creds_path = os.path.join(
                    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                    "google_vision_credentials.json",
                )

            if not os.path.exists(creds_path):
                cls._available = False
                raise GoogleVisionError(
                    f"Google Vision credentials not found at: {creds_path}"
                )

            credentials = service_account.Credentials.from_service_account_file(
                creds_path
            )
            cls._client = vision.ImageAnnotatorClient(credentials=credentials)
            cls._available = True
            logger.info("Google Cloud Vision client initialized successfully")
            return cls._client

        except ImportError:
            cls._available = False
            raise GoogleVisionError(
                "google-cloud-vision not installed. "
                "Install with: pip install google-cloud-vision"
            )
        except Exception as e:
            cls._available = False
            raise GoogleVisionError(f"Failed to initialize Vision client: {e}")

    @classmethod
    def is_available(cls) -> bool:
        """Check if Google Vision is configured and available."""
        if cls._available is not None:
            return cls._available
        try:
            cls._get_client()
            return True
        except GoogleVisionError:
            return False

    @classmethod
    def extract_text(cls, image_bytes: bytes) -> str:
        """Extract text from image using document_text_detection.

        Args:
            image_bytes: Raw image bytes (JPEG/PNG)

        Returns:
            Extracted full text string

        Raises:
            GoogleVisionError: On any failure (auth, network, timeout, empty)
        """
        client = cls._get_client()  # May raise GoogleVisionError

        from google.cloud import vision
        import google.api_core.exceptions
        import google.api_core.retry

        image = vision.Image(content=image_bytes)

        last_error = None
        for attempt in range(1, cls.MAX_RETRIES + 1):
            try:
                logger.info(f"Google Vision API attempt {attempt}/{cls.MAX_RETRIES}")

                # Call document_text_detection with timeout
                response = client.document_text_detection(
                    image=image,
                    timeout=cls.TIMEOUT,
                )

                # Check for API errors in response
                if response.error.message:
                    raise GoogleVisionError(
                        f"Vision API error: {response.error.message}"
                    )

                # Extract full text annotation
                full_text = ""
                if response.full_text_annotation:
                    full_text = response.full_text_annotation.text

                if not full_text or not full_text.strip():
                    raise GoogleVisionError("Vision API returned empty text")

                # Do NOT log the raw text (security requirement)
                logger.info(
                    f"Google Vision extracted {len(full_text)} chars "
                    f"on attempt {attempt}"
                )
                return full_text

            except GoogleVisionError:
                raise  # Re-raise our own errors immediately
            except google.api_core.exceptions.DeadlineExceeded:
                last_error = f"Timeout on attempt {attempt}"
                logger.warning(f"Google Vision timeout (attempt {attempt})")
            except google.api_core.exceptions.GoogleAPICallError as e:
                last_error = f"API error on attempt {attempt}: {e}"
                logger.warning(f"Google Vision API error (attempt {attempt}): {e}")
            except Exception as e:
                last_error = f"Unexpected error on attempt {attempt}: {e}"
                logger.warning(
                    f"Google Vision unexpected error (attempt {attempt}): {e}"
                )

        # All retries exhausted
        raise GoogleVisionError(
            f"Google Vision failed after {cls.MAX_RETRIES} attempts. "
            f"Last error: {last_error}"
        )
