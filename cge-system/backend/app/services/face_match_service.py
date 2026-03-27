"""
FaceMatchService — compares Aadhaar QR photo against live captured photo.
Uses face_recognition library (dlib-based) for accurate face comparison.

FALLBACK: If face_recognition/dlib cannot be installed (e.g., Railway deployment
without cmake/dlib build tools), falls back to a pixel-based histogram comparison
using numpy. This ensures the system never crashes even if dlib fails to install.

Production note: In a production deployment, a cloud-based face comparison API
(e.g., AWS Rekognition, Azure Face API) would be used instead of local dlib.
"""

import io
import logging
import numpy as np
from PIL import Image

logger = logging.getLogger("cge.face_match")

# Try to import face_recognition (requires dlib).
# If unavailable, fall back to histogram-based comparison.
try:
    import face_recognition
    FACE_RECOGNITION_AVAILABLE = True
    logger.info("face_recognition library loaded — using dlib-based face matching")
except ImportError:
    FACE_RECOGNITION_AVAILABLE = False
    logger.warning(
        "face_recognition/dlib not available — falling back to histogram-based comparison. "
        "Install dlib and face_recognition for accurate face matching."
    )

# Thresholds
FACE_RECOGNITION_THRESHOLD = 0.55   # score >= 0.55 = matched (dlib-based)
HISTOGRAM_THRESHOLD = 0.7           # score >= 0.7 = matched (fallback)


def compare_faces(aadhaar_image_bytes: bytes, live_image_bytes: bytes) -> dict:
    """
    Compare two face images and return match result.

    Args:
        aadhaar_image_bytes: Raw bytes of the Aadhaar QR photo
        live_image_bytes: Raw bytes of the live captured photo

    Returns:
        {
            "matched": bool,
            "score": float (0.0 to 1.0, rounded to 2 decimals),
            "method": "face_recognition" | "histogram_fallback",
            "error": str | None
        }

    Never raises an exception — wraps everything in try/except.
    """
    try:
        if FACE_RECOGNITION_AVAILABLE:
            return _compare_with_face_recognition(aadhaar_image_bytes, live_image_bytes)
        else:
            return _compare_with_histogram(aadhaar_image_bytes, live_image_bytes)
    except Exception as e:
        logger.error(f"Face comparison failed with unexpected error: {e}")
        return {
            "matched": False,
            "score": 0.0,
            "method": "error",
            "error": str(e),
        }


def _compare_with_face_recognition(aadhaar_bytes: bytes, live_bytes: bytes) -> dict:
    """Use face_recognition (dlib) for accurate face comparison."""
    try:
        # Decode images
        aadhaar_img = Image.open(io.BytesIO(aadhaar_bytes)).convert("RGB")
        live_img = Image.open(io.BytesIO(live_bytes)).convert("RGB")

        aadhaar_array = np.array(aadhaar_img)
        live_array = np.array(live_img)

        # Get face encodings
        aadhaar_encodings = face_recognition.face_encodings(aadhaar_array)
        if not aadhaar_encodings:
            logger.warning("No face detected in Aadhaar QR photo")
            return {
                "matched": False,
                "score": 0.0,
                "method": "face_recognition",
                "error": "no_face_detected_aadhaar",
            }

        live_encodings = face_recognition.face_encodings(live_array)
        if not live_encodings:
            logger.warning("No face detected in live captured photo")
            return {
                "matched": False,
                "score": 0.0,
                "method": "face_recognition",
                "error": "no_face_detected_live",
            }

        # Compute distance (lower = more similar)
        distance = face_recognition.face_distance([aadhaar_encodings[0]], live_encodings[0])[0]
        score = round(1.0 - float(distance), 2)
        matched = score >= FACE_RECOGNITION_THRESHOLD

        logger.info(f"Face match (dlib): distance={distance:.4f}, score={score}, matched={matched}")
        return {
            "matched": matched,
            "score": score,
            "method": "face_recognition",
            "error": None,
        }

    except Exception as e:
        logger.error(f"face_recognition comparison failed: {e}, falling back to histogram")
        return _compare_with_histogram(aadhaar_bytes, live_bytes)


def _compare_with_histogram(aadhaar_bytes: bytes, live_bytes: bytes) -> dict:
    """
    Fallback: pixel-based similarity using grayscale histogram comparison.
    This is less accurate than face_recognition but works without dlib.
    Uses normalized histogram correlation (cv2.HISTCMP_CORREL equivalent).
    """
    try:
        # Decode and convert to grayscale
        aadhaar_img = Image.open(io.BytesIO(aadhaar_bytes)).convert("L")
        live_img = Image.open(io.BytesIO(live_bytes)).convert("L")

        # Resize both to same dimensions for fair comparison
        target_size = (128, 128)
        aadhaar_img = aadhaar_img.resize(target_size, Image.LANCZOS)
        live_img = live_img.resize(target_size, Image.LANCZOS)

        # Compute normalized histograms (256 bins)
        aadhaar_hist = np.histogram(np.array(aadhaar_img), bins=256, range=(0, 256))[0].astype(np.float64)
        live_hist = np.histogram(np.array(live_img), bins=256, range=(0, 256))[0].astype(np.float64)

        # Normalize
        aadhaar_hist /= (aadhaar_hist.sum() + 1e-10)
        live_hist /= (live_hist.sum() + 1e-10)

        # Correlation-based similarity (equivalent to cv2.HISTCMP_CORREL)
        mean_a = np.mean(aadhaar_hist)
        mean_l = np.mean(live_hist)
        numerator = np.sum((aadhaar_hist - mean_a) * (live_hist - mean_l))
        denominator = np.sqrt(
            np.sum((aadhaar_hist - mean_a) ** 2) * np.sum((live_hist - mean_l) ** 2)
        )

        if denominator < 1e-10:
            score = 0.0
        else:
            score = round(float(numerator / denominator), 2)

        # Clamp to [0, 1]
        score = max(0.0, min(1.0, score))
        matched = score >= HISTOGRAM_THRESHOLD

        logger.info(f"Face match (histogram fallback): score={score}, matched={matched}")
        return {
            "matched": matched,
            "score": score,
            "method": "histogram_fallback",
            "error": None,
        }

    except Exception as e:
        logger.error(f"Histogram comparison failed: {e}")
        return {
            "matched": False,
            "score": 0.0,
            "method": "histogram_fallback",
            "error": str(e),
        }
