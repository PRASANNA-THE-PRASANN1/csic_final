"""
OCRService — Fully offline OCR + structured data extraction pipeline.

Pipeline:
  Step 1: Image preprocessing (OpenCV)
  Step 2: Text recognition (PaddleOCR → Tesseract fallback)
  Step 3: Structured field extraction (regex + heuristic + optional Ollama LLM)
  Step 4: Validation layer (Aadhaar, IFSC, phone, account)
  Step 5: Confidence scoring (per-field 0.0–1.0)
  Step 6: Secure encrypted storage

Privacy: NO external API calls. All processing is local.
"""

import re
import os
import io
import json
import math
import logging
import hashlib
from typing import Dict, Any, Optional, List, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# ── Lazy-loaded OCR engines ─────────────────────────────────────────

_paddle_ocr_instance = None
_paddle_available = None


def _get_paddle_ocr():
    """Lazy-load PaddleOCR (heavy init, singleton)."""
    global _paddle_ocr_instance, _paddle_available
    if _paddle_available is False:
        return None
    if _paddle_ocr_instance is not None:
        return _paddle_ocr_instance

    # Skip the slow model-source connectivity check in PaddleOCR 3.x
    os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")

    try:
        from paddleocr import PaddleOCR

        # Try different parameter sets for version compatibility.
        # PaddleOCR 3.x removed use_gpu (auto-detects device).
        # PaddleOCR 2.x requires use_gpu=False for CPU.
        param_sets = [
            # PaddleOCR 3.x — no use_gpu, show_log, or det_db_thresh
            dict(lang='hi'),
            # PaddleOCR 3.x — English only
            dict(lang='en'),
            # PaddleOCR 2.7+ — with show_log
            dict(use_angle_cls=True, lang='hi', use_gpu=False, show_log=False,
                 det_db_thresh=0.3, rec_batch_num=6),
            # PaddleOCR 2.x — no show_log
            dict(use_angle_cls=True, lang='hi', use_gpu=False,
                 det_db_thresh=0.3, rec_batch_num=6),
            # Minimal PaddleOCR 2.x
            dict(lang='hi', use_gpu=False),
            # Fallback: English-only (2.x)
            dict(lang='en', use_gpu=False),
        ]

        for i, params in enumerate(param_sets):
            try:
                _paddle_ocr_instance = PaddleOCR(**params)
                _paddle_available = True
                logger.info(f"PaddleOCR loaded successfully (param set {i+1})")
                return _paddle_ocr_instance
            except (TypeError, ValueError) as te:
                logger.debug(f"PaddleOCR param set {i+1} failed: {te}")
                continue
            except Exception as inner_e:
                logger.debug(f"PaddleOCR param set {i+1} error: {inner_e}")
                continue

        logger.warning("PaddleOCR: all parameter combinations failed")
        _paddle_available = False
        return None
    except ImportError:
        logger.warning("PaddleOCR not installed. Install with: pip install paddleocr paddlepaddle")
        _paddle_available = False
        return None
    except Exception as e:
        logger.warning(f"PaddleOCR not available: {e}. Will fall back to Tesseract.")
        _paddle_available = False
        return None


# ── Field label patterns (Hindi + English) ───────────────────────────

FIELD_LABELS = {
    "name": [
        r"(?:नाम|name|farmer\s*name|किसान\s*का\s*नाम|applicant\s*name|आवेदक\s*का\s*नाम)",
    ],
    "account_number": [
        r"(?:खाता\s*(?:संख्या|नं|नंबर)|account\s*(?:no|number|num)|a/c\s*(?:no|number)|बैंक\s*खाता)",
    ],
    "ifsc": [
        r"(?:ifsc\s*(?:code)?|आईएफएससी)",
    ],
    "phone_number": [
        r"(?:फोन|phone|mobile|मोबाइल|contact|संपर्क|दूरभाष)",
    ],
    "aadhaar_number": [
        r"(?:आधार|aadhaar|aadhar|uid|आधार\s*(?:संख्या|नं|नंबर))",
    ],
    "loan_amount": [
        r"(?:ऋण\s*(?:राशि|रकम)|loan\s*amount|amount\s*(?:requested|required)|राशि|रुपये|₹)",
    ],
    "annual_income": [
        r"(?:वार्षिक\s*आय|annual\s*income|yearly\s*income|आय|income)",
    ],
    "land_ownership": [
        r"(?:भूमि|land|ज़मीन|जमीन|कृषि\s*भूमि|land\s*(?:area|ownership|holding)|एकड़|hectare|बीघा)",
    ],
    "loan_reason": [
        r"(?:ऋण\s*(?:का\s*)?(?:कारण|उद्देश्य)|purpose|reason|loan\s*(?:purpose|reason)|उद्देश्य)",
    ],
}


# ═══════════════════════════════════════════════════════════════════════
#  STEP 1: IMAGE PREPROCESSING
# ═══════════════════════════════════════════════════════════════════════

class ImagePreprocessor:
    """OpenCV-based image preprocessing for handwritten forms."""

    @staticmethod
    def preprocess(image_bytes: bytes) -> np.ndarray:
        """Full preprocessing pipeline: grayscale → threshold → denoise → deskew."""
        import cv2

        # Decode image
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError("Could not decode image")

        # 1. Convert to grayscale
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # 2. Noise removal with bilateral filter (preserves edges)
        denoised = cv2.bilateralFilter(gray, d=9, sigmaColor=75, sigmaSpace=75)

        # 3. Adaptive thresholding (handles uneven lighting in handwritten forms)
        thresh = cv2.adaptiveThreshold(
            denoised, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            blockSize=11, C=2,
        )

        # 4. Morphological opening (removes small dots/noise)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
        cleaned = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel, iterations=1)

        # 5. Deskew
        deskewed = ImagePreprocessor._deskew(cleaned)

        return deskewed

    @staticmethod
    def _deskew(image: np.ndarray) -> np.ndarray:
        """Auto-rotate tilted images using Hough line detection."""
        import cv2

        # Detect lines
        edges = cv2.Canny(image, 50, 150, apertureSize=3)
        lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=100,
                                minLineLength=100, maxLineGap=10)

        if lines is None or len(lines) < 3:
            return image

        # Compute dominant angle
        angles = []
        for line in lines:
            x1, y1, x2, y2 = line[0]
            angle = math.degrees(math.atan2(y2 - y1, x2 - x1))
            if abs(angle) < 30:  # Only near-horizontal lines
                angles.append(angle)

        if not angles:
            return image

        median_angle = float(np.median(angles))
        if abs(median_angle) < 0.5:  # Already straight
            return image

        # Rotate
        h, w = image.shape[:2]
        center = (w // 2, h // 2)
        M = cv2.getRotationMatrix2D(center, median_angle, 1.0)
        rotated = cv2.warpAffine(image, M, (w, h),
                                 flags=cv2.INTER_CUBIC,
                                 borderMode=cv2.BORDER_REPLICATE)
        return rotated

    @staticmethod
    def to_pil(image: np.ndarray):
        """Convert numpy array to PIL Image."""
        from PIL import Image
        return Image.fromarray(image)

    @staticmethod
    def to_bytes(image: np.ndarray) -> bytes:
        """Convert numpy array to JPEG bytes."""
        import cv2
        _, buffer = cv2.imencode('.jpg', image)
        return buffer.tobytes()


# ═══════════════════════════════════════════════════════════════════════
#  STEP 2: OCR TEXT RECOGNITION
# ═══════════════════════════════════════════════════════════════════════

class TextRecognizer:
    """Multi-engine OCR with PaddleOCR primary + Tesseract fallback."""

    @staticmethod
    def recognize(preprocessed_image: np.ndarray) -> Dict[str, Any]:
        """Run OCR and return structured text result."""
        # Try PaddleOCR first
        result = TextRecognizer._paddle_ocr(preprocessed_image)
        if result and result["full_text"].strip():
            return result

        # Fallback to Tesseract
        result = TextRecognizer._tesseract_ocr(preprocessed_image)
        if result and result["full_text"].strip():
            return result

        # Final fallback — empty
        return {
            "engine": "none",
            "full_text": "",
            "lines": [],
            "words": [],
            "avg_confidence": 0.0,
        }

    @staticmethod
    def _paddle_ocr(image: np.ndarray) -> Optional[Dict[str, Any]]:
        """PaddleOCR recognition."""
        ocr = _get_paddle_ocr()
        if ocr is None:
            return None

        try:
            # PaddleOCR 3.x may not support cls= parameter
            try:
                results = ocr.ocr(image, cls=True)
            except TypeError:
                results = ocr.ocr(image)

            if not results or not results[0]:
                return None

            lines = []
            words = []
            full_parts = []
            confidences = []

            for line_result in results[0]:
                # Handle both v2.x format [box, (text, conf)]
                # and potential v3.x format variations
                try:
                    if isinstance(line_result, (list, tuple)) and len(line_result) == 2:
                        box, text_conf = line_result
                        if isinstance(text_conf, (list, tuple)) and len(text_conf) == 2:
                            text, conf = text_conf
                        elif isinstance(text_conf, dict):
                            text = text_conf.get("text", "")
                            conf = text_conf.get("confidence", 0.5)
                        else:
                            continue
                    else:
                        continue

                    lines.append({
                        "text": str(text),
                        "confidence": float(conf),
                        "box": [[int(p[0]), int(p[1])] for p in box] if box else [],
                    })
                    full_parts.append(str(text))
                    confidences.append(float(conf))

                    # Split into words
                    for word in str(text).split():
                        words.append({"text": word, "confidence": float(conf)})
                except (ValueError, IndexError, TypeError) as parse_err:
                    logger.debug(f"Skipping OCR line result: {parse_err}")
                    continue

            if not full_parts:
                return None

            avg_conf = sum(confidences) / len(confidences) if confidences else 0.0

            return {
                "engine": "paddleocr",
                "full_text": "\n".join(full_parts),
                "lines": lines,
                "words": words,
                "avg_confidence": round(avg_conf, 3),
            }
        except Exception as e:
            logger.warning(f"PaddleOCR recognition failed: {e}")
            return None

    @staticmethod
    def _tesseract_ocr(image: np.ndarray, psm: int = None, whitelist: str = None) -> Optional[Dict[str, Any]]:
        """Tesseract OCR fallback.
        Args:
            psm: Page segmentation mode (e.g., 6=uniform block, 7=single line)
            whitelist: Character whitelist (e.g., '0123456789' for digits-only)
        """
        try:
            import pytesseract
            from PIL import Image

            # Fix 2: Check TESSERACT_PATH env var first
            env_path = os.getenv('TESSERACT_PATH', '').strip()
            if env_path and os.path.exists(env_path):
                pytesseract.pytesseract.tesseract_cmd = env_path
            else:
                # Fallback: check common Windows install paths
                import platform
                if platform.system() == 'Windows':
                    import shutil
                    if not shutil.which('tesseract'):
                        common_paths = [
                            r'C:\Program Files\Tesseract-OCR\tesseract.exe',
                            r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe',
                            r'C:\Users\{}\AppData\Local\Tesseract-OCR\tesseract.exe'.format(
                                os.environ.get('USERNAME', '')),
                        ]
                        for tpath in common_paths:
                            if os.path.exists(tpath):
                                pytesseract.pytesseract.tesseract_cmd = tpath
                                break
                        else:
                            logger.warning(
                                "Tesseract not found. Set TESSERACT_PATH in .env or "
                                "install from: https://github.com/UB-Mannheim/tesseract/wiki"
                            )
                            return None

            pil_img = Image.fromarray(image)

            # Build Tesseract config string
            tess_config = ''
            if psm is not None:
                tess_config += f' --psm {psm}'
            if whitelist:
                tess_config += f' -c tessedit_char_whitelist={whitelist}'

            # Try Hindi+English, fall back to English only
            try:
                full_text = pytesseract.image_to_string(pil_img, lang="hin+eng", config=tess_config)
                data = pytesseract.image_to_data(pil_img, lang="hin+eng",
                                                 output_type=pytesseract.Output.DICT,
                                                 config=tess_config)
            except pytesseract.TesseractError:
                logger.info("Hindi language data not available, using English only")
                full_text = pytesseract.image_to_string(pil_img, lang="eng", config=tess_config)
                data = pytesseract.image_to_data(pil_img, lang="eng",
                                                 output_type=pytesseract.Output.DICT,
                                                 config=tess_config)

            words = []
            confidences = []
            for i, word in enumerate(data["text"]):
                if word.strip():
                    conf = int(data["conf"][i])
                    if conf > 0:
                        words.append({"text": word, "confidence": conf / 100.0})
                        confidences.append(conf / 100.0)

            avg_conf = sum(confidences) / len(confidences) if confidences else 0.0

            # Build lines from text
            lines = []
            for line_text in full_text.split("\n"):
                if line_text.strip():
                    lines.append({"text": line_text.strip(), "confidence": avg_conf})

            return {
                "engine": "tesseract",
                "full_text": full_text,
                "lines": lines,
                "words": words,
                "avg_confidence": round(avg_conf, 3),
            }
        except ImportError:
            logger.warning("pytesseract not installed. Install with: pip install pytesseract")
            return None
        except Exception as e:
            logger.warning(f"Tesseract OCR failed: {e}")
            return None


# ═══════════════════════════════════════════════════════════════════════
#  STEP 3: STRUCTURED FIELD EXTRACTION
# ═══════════════════════════════════════════════════════════════════════

class FieldExtractor:
    """Extract structured fields from raw OCR text using regex + heuristics."""

    @staticmethod
    def extract(ocr_result: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        """Extract all 9 fields from OCR output."""
        text = ocr_result.get("full_text", "")
        lines = ocr_result.get("lines", [])

        # Build a map of line_text -> confidence for scoring later
        line_conf_map = {}
        for line in lines:
            line_conf_map[line["text"]] = line.get("confidence", 0.5)

        fields = {}

        # 1. Name
        fields["name"] = FieldExtractor._extract_name(text, lines)

        # 2. Account number
        fields["account_number"] = FieldExtractor._extract_account_number(text, lines)

        # 3. IFSC code
        fields["ifsc"] = FieldExtractor._extract_ifsc(text)

        # 4. Phone number
        fields["phone_number"] = FieldExtractor._extract_phone(text)

        # 5. Aadhaar number
        fields["aadhaar_number"] = FieldExtractor._extract_aadhaar(text)

        # 6. Loan amount
        fields["loan_amount"] = FieldExtractor._extract_amount(text, "loan_amount")

        # 7. Annual income
        fields["annual_income"] = FieldExtractor._extract_amount(text, "annual_income")

        # 8. Land ownership
        fields["land_ownership"] = FieldExtractor._extract_land(text, lines)

        # 9. Loan reason / purpose
        fields["loan_reason"] = FieldExtractor._extract_reason(text, lines)

        # Apply OCR line confidence to extracted fields
        for field_key, field_data in fields.items():
            if field_data["value"] and field_data.get("source_line"):
                src = field_data["source_line"]
                for lt, lc in line_conf_map.items():
                    if src in lt or lt in src:
                        field_data["ocr_confidence"] = lc
                        break

        return fields

    @staticmethod
    def _find_adjacent_value(text: str, lines: List[Dict], label_patterns: List[str]) -> Tuple[Optional[str], Optional[str]]:
        """Find value adjacent to a label in the OCR text."""
        for pattern in label_patterns:
            for line in lines:
                lt = line["text"]
                match = re.search(pattern, lt, re.IGNORECASE)
                if match:
                    # Value is after the label in the same line
                    after = lt[match.end():].strip().strip(':').strip('-').strip('–').strip()
                    if after:
                        return after, lt
            # Also try multi-line: label on one line, value on next
            line_texts = [l["text"] for l in lines]
            for i, lt in enumerate(line_texts):
                if re.search(pattern, lt, re.IGNORECASE) and i + 1 < len(line_texts):
                    next_line = line_texts[i + 1].strip()
                    if next_line and not any(re.search(p, next_line, re.IGNORECASE) for lps in FIELD_LABELS.values() for p in lps):
                        return next_line, lt
        return None, None

    @staticmethod
    def _extract_name(text: str, lines: List[Dict]) -> Dict[str, Any]:
        val, src = FieldExtractor._find_adjacent_value(text, lines, FIELD_LABELS["name"])
        if val:
            # Clean: remove digits, special chars
            cleaned = re.sub(r'[0-9₹:;\-–/\\|]', '', val).strip()
            if len(cleaned) >= 2:
                return {"value": cleaned, "method": "label_match", "source_line": src, "ocr_confidence": 0.5}
        return {"value": None, "method": "not_found", "source_line": None, "ocr_confidence": 0.0}

    @staticmethod
    def _extract_account_number(text: str, lines: List[Dict]) -> Dict[str, Any]:
        # Try label-adjacent first
        val, src = FieldExtractor._find_adjacent_value(text, lines, FIELD_LABELS["account_number"])
        if val:
            digits = re.sub(r'\D', '', val)
            if 9 <= len(digits) <= 18:
                return {"value": digits, "method": "label_match", "source_line": src, "ocr_confidence": 0.5}

        # Fallback: find 9-18 digit sequences not matching Aadhaar/phone
        for match in re.finditer(r'\b(\d{9,18})\b', text):
            num = match.group(1)
            if len(num) != 12 and len(num) != 10:  # Not Aadhaar or phone
                return {"value": num, "method": "regex_scan", "source_line": None, "ocr_confidence": 0.3}

        return {"value": None, "method": "not_found", "source_line": None, "ocr_confidence": 0.0}

    @staticmethod
    def _extract_ifsc(text: str) -> Dict[str, Any]:
        match = re.search(r'\b([A-Z]{4}0[A-Z0-9]{6})\b', text.upper())
        if match:
            return {"value": match.group(1), "method": "regex_pattern", "source_line": None, "ocr_confidence": 0.8}
        return {"value": None, "method": "not_found", "source_line": None, "ocr_confidence": 0.0}

    @staticmethod
    def _extract_phone(text: str) -> Dict[str, Any]:
        # Indian mobile: 10 digits starting with 6-9
        for match in re.finditer(r'(?:(?:\+91|91|0)?[\s\-]?)?([6-9]\d{9})\b', text):
            return {"value": match.group(1), "method": "regex_pattern", "source_line": None, "ocr_confidence": 0.7}
        return {"value": None, "method": "not_found", "source_line": None, "ocr_confidence": 0.0}

    @staticmethod
    def _extract_aadhaar(text: str) -> Dict[str, Any]:
        # Aadhaar: 12 digits, possibly with spaces/dashes
        for match in re.finditer(r'\b(\d{4}[\s\-]?\d{4}[\s\-]?\d{4})\b', text):
            digits = re.sub(r'\D', '', match.group(1))
            if len(digits) == 12 and digits[0] != '0' and digits[0] != '1':
                return {"value": digits, "method": "regex_pattern", "source_line": None, "ocr_confidence": 0.7}
        return {"value": None, "method": "not_found", "source_line": None, "ocr_confidence": 0.0}

    @staticmethod
    def _extract_amount(text: str, field_type: str) -> Dict[str, Any]:
        """Extract numeric amount, searching near the relevant label."""
        labels = FIELD_LABELS.get(field_type, [])
        for pattern in labels:
            match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
            if match:
                # Look for numbers after the label
                after_text = text[match.end():match.end() + 100]
                amt_match = re.search(r'[₹Rs\.]*\s*([\d,]+(?:\.\d{1,2})?)', after_text)
                if amt_match:
                    try:
                        val = float(amt_match.group(1).replace(',', ''))
                        return {"value": val, "method": "label_match", "source_line": None, "ocr_confidence": 0.6}
                    except ValueError:
                        pass

        # Fallback: find currency-prefixed amounts
        for match in re.finditer(r'[₹Rs\.]+\s*([\d,]+(?:\.\d{1,2})?)', text):
            try:
                val = float(match.group(1).replace(',', ''))
                if val > 100:  # Ignore tiny numbers
                    return {"value": val, "method": "regex_scan", "source_line": None, "ocr_confidence": 0.3}
            except ValueError:
                pass

        return {"value": None, "method": "not_found", "source_line": None, "ocr_confidence": 0.0}

    @staticmethod
    def _extract_land(text: str, lines: List[Dict]) -> Dict[str, Any]:
        val, src = FieldExtractor._find_adjacent_value(text, lines, FIELD_LABELS["land_ownership"])
        if val:
            return {"value": val, "method": "label_match", "source_line": src, "ocr_confidence": 0.5}

        # Look for acre/hectare/bigha patterns
        match = re.search(r'(\d+(?:\.\d+)?)\s*(?:एकड़|acre|hectare|हेक्टेयर|bigha|बीघा)', text, re.IGNORECASE)
        if match:
            return {"value": match.group(0), "method": "regex_pattern", "source_line": None, "ocr_confidence": 0.6}

        return {"value": None, "method": "not_found", "source_line": None, "ocr_confidence": 0.0}

    @staticmethod
    def _extract_reason(text: str, lines: List[Dict]) -> Dict[str, Any]:
        val, src = FieldExtractor._find_adjacent_value(text, lines, FIELD_LABELS["loan_reason"])
        if val:
            return {"value": val[:200], "method": "label_match", "source_line": src, "ocr_confidence": 0.5}
        return {"value": None, "method": "not_found", "source_line": None, "ocr_confidence": 0.0}


# ═══════════════════════════════════════════════════════════════════════
#  STEP 3b: LOCAL VISION MODEL EXTRACTION (Ollama + LLaVA)
# ═══════════════════════════════════════════════════════════════════════

class LLMFieldExtractor:
    """Extract fields using local LLaVA 7B vision model via Ollama.

    Two modes:
      1. Vision mode (primary): sends image directly to LLaVA for visual extraction
      2. Text mode (fallback): sends raw OCR text to a text model like Mistral

    Requires: Ollama running locally with `ollama pull llava:7b`
    """

    OLLAMA_BASE = os.getenv("OLLAMA_URL", "http://localhost:11434")
    OLLAMA_URL = f"{OLLAMA_BASE}/api/generate"
    VISION_MODEL = os.getenv("OLLAMA_MODEL", "llava:7b")
    TEXT_MODEL = "mistral"  # Fallback text-only model

    _available = None  # Cache availability check
    _has_vision_model = None

    @classmethod
    def is_available(cls) -> bool:
        """Check if Ollama is running locally."""
        if cls._available is not None:
            return cls._available
        try:
            import urllib.request
            req = urllib.request.Request(
                f"{cls.OLLAMA_BASE}/api/tags",
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=2) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode())
                    model_names = [m.get("name", "") for m in data.get("models", [])]
                    cls._has_vision_model = any(
                        cls.VISION_MODEL.split(":")[0] in name for name in model_names
                    )
                    cls._available = True
                    if cls._has_vision_model:
                        logger.info(f"Ollama available with vision model: {cls.VISION_MODEL}")
                    else:
                        logger.info(f"Ollama available but {cls.VISION_MODEL} not found. Available: {model_names}")
                    return True
        except Exception:
            pass
        cls._available = False
        return False

    @classmethod
    def extract_with_vision(cls, image_bytes: bytes, field_name: str = None) -> Optional[Dict[str, Any]]:
        """Send image directly to LLaVA vision model for structured extraction.

        Args:
            image_bytes: Raw image bytes (JPEG/PNG)
            field_name: If provided, extract only this specific field
        Returns:
            Dict of extracted fields, or None on failure
        """
        if not cls.is_available() or not cls._has_vision_model:
            return None

        import base64
        image_b64 = base64.b64encode(image_bytes).decode()

        if field_name:
            prompt = (
                f"You are extracting data from an Indian agricultural loan application form. "
                f"Extract only the value for the field: {field_name}. "
                f"The text may be in Hindi, English, or numerals. "
                f"Return ONLY the extracted value. If empty or illegible return: EMPTY"
            )
        else:
            prompt = (
                "Extract all filled values from this Indian agricultural loan application form. "
                "Return a JSON object with these exact keys: "
                "name, account_number, ifsc, phone_number, aadhaar_number, "
                "loan_amount, annual_income, land_ownership, loan_reason. "
                "For aadhaar_number extract 12 digits only. "
                "For amounts extract numbers only without currency symbols. "
                "If a field is empty use null. "
                "Return ONLY valid JSON."
            )

        try:
            import urllib.request
            payload = json.dumps({
                "model": cls.VISION_MODEL,
                "prompt": prompt,
                "images": [image_b64],
                "stream": False,
                "options": {"temperature": 0.1, "num_predict": 500},
            }).encode()

            req = urllib.request.Request(
                cls.OLLAMA_URL,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read().decode())
                response_text = result.get("response", "")

                if field_name:
                    # Single field mode — return raw extracted value
                    cleaned = response_text.strip()
                    return {field_name: None if cleaned == "EMPTY" else cleaned}

                # Full-form mode — parse JSON
                json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', response_text, re.DOTALL)
                if json_match:
                    extracted = json.loads(json_match.group())
                    logger.info(f"LLaVA vision extracted {len([v for v in extracted.values() if v])} fields")
                    return extracted
        except Exception as e:
            logger.warning(f"LLaVA vision extraction failed: {e}")

        return None

    @staticmethod
    def extract(raw_text: str) -> Optional[Dict[str, Any]]:
        """Fallback: send raw OCR text to a text model for structured extraction."""
        if not LLMFieldExtractor.is_available():
            return None

        prompt = f"""Extract the following fields from this handwritten loan application text.
Return ONLY valid JSON with these keys: name, account_number, ifsc, phone_number, aadhaar_number, loan_amount, annual_income, land_ownership, loan_reason.
If a field is not found, set its value to null.

TEXT:
{raw_text[:2000]}

JSON:"""

        try:
            import urllib.request
            payload = json.dumps({
                "model": LLMFieldExtractor.TEXT_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.1, "num_predict": 500},
            }).encode()

            req = urllib.request.Request(
                LLMFieldExtractor.OLLAMA_URL,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode())
                response_text = result.get("response", "")

                # Parse JSON from response
                json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', response_text, re.DOTALL)
                if json_match:
                    extracted = json.loads(json_match.group())
                    return extracted
        except Exception as e:
            logger.warning(f"Ollama text extraction failed: {e}")

        return None


# ═══════════════════════════════════════════════════════════════════════
#  STEP 3c: FORM REGION EXTRACTION
# ═══════════════════════════════════════════════════════════════════════

# Percentage-based coordinates (left, top, right, bottom) matching the
# Indian agricultural loan form layout.  Resolution-independent.
FORM_REGIONS = {
    "name":           (0.08, 0.18, 0.42, 0.30),
    "father_name":    (0.42, 0.18, 0.72, 0.30),
    "photo_box":      (0.72, 0.10, 0.95, 0.35),
    "aadhaar_number": (0.08, 0.30, 0.52, 0.42),
    "phone_number":   (0.52, 0.30, 0.72, 0.42),
    "account_number": (0.08, 0.42, 0.55, 0.54),
    "ifsc":           (0.55, 0.42, 0.95, 0.54),
    "loan_amount":    (0.08, 0.54, 0.52, 0.66),
    "annual_income":  (0.52, 0.54, 0.95, 0.66),
    "loan_reason":    (0.08, 0.66, 0.95, 0.95),
}

# Tesseract page-segmentation modes optimal for each field type
FIELD_PSM = {
    "name": 7,            # single line
    "father_name": 7,
    "aadhaar_number": 6,  # uniform block of text (boxed digits)
    "phone_number": 6,
    "account_number": 6,
    "ifsc": 7,
    "loan_amount": 7,
    "annual_income": 7,
    "loan_reason": 6,     # block of text
}

# Character whitelists for digit-only fields
FIELD_WHITELIST = {
    "aadhaar_number": "0123456789 -",
    "phone_number": "0123456789+- ",
    "account_number": "0123456789",
    "loan_amount": "0123456789,.",
    "annual_income": "0123456789,.",
}


class FormRegionExtractor:
    """Crop form regions and run per-field OCR for improved accuracy."""

    @staticmethod
    def crop_region(image_bytes: bytes, region_name: str) -> Optional[bytes]:
        """Crop a named region from the form image.
        Returns JPEG bytes of the cropped region, or None.
        """
        if region_name not in FORM_REGIONS:
            return None
        try:
            import cv2
            nparr = np.frombuffer(image_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if img is None:
                return None
            h, w = img.shape[:2]
            left, top, right, bottom = FORM_REGIONS[region_name]
            x1, y1, x2, y2 = int(left * w), int(top * h), int(right * w), int(bottom * h)
            cropped = img[y1:y2, x1:x2]
            if cropped.size == 0:
                return None
            _, buf = cv2.imencode('.jpg', cropped)
            return buf.tobytes()
        except Exception as e:
            logger.debug(f"Region crop failed for {region_name}: {e}")
            return None

    @staticmethod
    def crop_all_regions(image_bytes: bytes) -> Dict[str, bytes]:
        """Crop all defined regions and return a dict of name → JPEG bytes."""
        regions = {}
        for name in FORM_REGIONS:
            cropped = FormRegionExtractor.crop_region(image_bytes, name)
            if cropped:
                regions[name] = cropped
        return regions

    @staticmethod
    def extract_photo_box(image_bytes: bytes) -> Dict[str, Any]:
        """Crop the photo box region and run OpenCV Haar cascade face detection.

        Returns:
            {"face_found": bool, "face_bytes": bytes|None, "face_coords": tuple|None}
        """
        photo_bytes = FormRegionExtractor.crop_region(image_bytes, "photo_box")
        if not photo_bytes:
            return {"face_found": False, "face_bytes": None, "face_coords": None}

        try:
            import cv2
            nparr = np.frombuffer(photo_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if img is None:
                return {"face_found": False, "face_bytes": None, "face_coords": None}

            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

            # Use OpenCV's bundled Haar cascade — no additional download needed
            cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
            face_cascade = cv2.CascadeClassifier(cascade_path)
            faces = face_cascade.detectMultiScale(
                gray, scaleFactor=1.1, minNeighbors=4, minSize=(30, 30)
            )

            if len(faces) > 0:
                # Take the largest detected face
                x, y, fw, fh = max(faces, key=lambda f: f[2] * f[3])
                return {
                    "face_found": True,
                    "face_bytes": photo_bytes,
                    "face_coords": (int(x), int(y), int(fw), int(fh)),
                }
            else:
                return {"face_found": False, "face_bytes": photo_bytes, "face_coords": None}
        except Exception as e:
            logger.warning(f"Photo box face detection failed: {e}")
            return {"face_found": False, "face_bytes": None, "face_coords": None}

    @staticmethod
    def run_per_field_ocr(image_bytes: bytes) -> Dict[str, Dict[str, Any]]:
        """Run region-aware Tesseract OCR on each cropped field.

        Returns dict of field_name → {value, confidence, method}.
        Uses field-specific PSM modes and whitelists.
        """
        results = {}
        regions = FormRegionExtractor.crop_all_regions(image_bytes)

        for field_name, region_bytes in regions.items():
            if field_name == "photo_box":
                continue  # Photo box is not OCR'd

            psm = FIELD_PSM.get(field_name)
            whitelist = FIELD_WHITELIST.get(field_name)

            try:
                # Preprocess the cropped region
                preprocessed = ImagePreprocessor.preprocess(region_bytes)
                # Run Tesseract with field-specific settings
                ocr_result = TextRecognizer._tesseract_ocr(preprocessed, psm=psm, whitelist=whitelist)
                if ocr_result and ocr_result["full_text"].strip():
                    text = ocr_result["full_text"].strip()
                    conf = ocr_result["avg_confidence"]
                    results[field_name] = {
                        "value": text,
                        "confidence": conf,
                        "method": "region_tesseract",
                        "source_line": text,
                        "ocr_confidence": conf,
                    }
                    continue
            except Exception as e:
                logger.debug(f"Region OCR failed for {field_name}: {e}")

            results[field_name] = {
                "value": None, "confidence": 0.0, "method": "not_found",
                "source_line": None, "ocr_confidence": 0.0,
            }

        return results


# ═══════════════════════════════════════════════════════════════════════
#  STEP 4: VALIDATION LAYER
# ═══════════════════════════════════════════════════════════════════════

class FieldValidator:
    """Rule-based validation for each extracted field."""

    # Verhoeff checksum tables for Aadhaar validation
    _VERHOEFF_D = [
        [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
        [1, 2, 3, 4, 0, 6, 7, 8, 9, 5],
        [2, 3, 4, 0, 1, 7, 8, 9, 5, 6],
        [3, 4, 0, 1, 2, 8, 9, 5, 6, 7],
        [4, 0, 1, 2, 3, 9, 5, 6, 7, 8],
        [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
        [6, 5, 9, 8, 7, 1, 0, 4, 3, 2],
        [7, 6, 5, 9, 8, 2, 1, 0, 4, 3],
        [8, 7, 6, 5, 9, 3, 2, 1, 0, 4],
        [9, 8, 7, 6, 5, 4, 3, 2, 1, 0],
    ]
    _VERHOEFF_P = [
        [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
        [1, 5, 7, 6, 2, 8, 3, 0, 9, 4],
        [5, 8, 0, 3, 7, 9, 6, 1, 4, 2],
        [8, 9, 1, 6, 0, 4, 3, 5, 2, 7],
        [9, 4, 5, 3, 1, 2, 6, 8, 7, 0],
        [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
        [2, 7, 9, 3, 8, 0, 6, 4, 1, 5],
        [7, 0, 4, 6, 9, 1, 3, 2, 5, 8],
    ]

    @staticmethod
    def validate_all(fields: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        """Validate all fields and add validation_passed + validation_error."""
        validators = {
            "name": FieldValidator._validate_name,
            "account_number": FieldValidator._validate_account,
            "ifsc": FieldValidator._validate_ifsc,
            "phone_number": FieldValidator._validate_phone,
            "aadhaar_number": FieldValidator._validate_aadhaar,
            "loan_amount": FieldValidator._validate_amount,
            "annual_income": FieldValidator._validate_income,
            "land_ownership": FieldValidator._validate_land,
            "loan_reason": FieldValidator._validate_reason,
        }

        for key, field_data in fields.items():
            validator = validators.get(key)
            if validator and field_data.get("value") is not None:
                passed, error = validator(field_data["value"])
                field_data["validation_passed"] = passed
                field_data["validation_error"] = error
            elif field_data.get("value") is None:
                field_data["validation_passed"] = False
                field_data["validation_error"] = "Field not detected"
            else:
                field_data["validation_passed"] = True
                field_data["validation_error"] = None

        return fields

    @staticmethod
    def _validate_name(value: str) -> Tuple[bool, Optional[str]]:
        if not value or len(value.strip()) < 2:
            return False, "Name too short"
        if re.search(r'\d', value):
            return False, "Name contains digits"
        return True, None

    @staticmethod
    def _validate_account(value: str) -> Tuple[bool, Optional[str]]:
        digits = re.sub(r'\D', '', str(value))
        if len(digits) < 9:
            return False, f"Too short ({len(digits)} digits, need 9-18)"
        if len(digits) > 18:
            return False, f"Too long ({len(digits)} digits, max 18)"
        return True, None

    @staticmethod
    def _validate_ifsc(value: str) -> Tuple[bool, Optional[str]]:
        if not re.match(r'^[A-Z]{4}0[A-Z0-9]{6}$', str(value).upper()):
            return False, "Invalid IFSC format (expected: ABCD0XXXXXX)"
        return True, None

    @staticmethod
    def _validate_phone(value: str) -> Tuple[bool, Optional[str]]:
        digits = re.sub(r'\D', '', str(value))
        if len(digits) != 10:
            return False, f"Must be 10 digits (got {len(digits)})"
        if digits[0] not in '6789':
            return False, f"Must start with 6-9 (starts with {digits[0]})"
        return True, None

    @staticmethod
    def _validate_aadhaar(value: str) -> Tuple[bool, Optional[str]]:
        digits = re.sub(r'\D', '', str(value))
        if len(digits) != 12:
            return False, f"Must be 12 digits (got {len(digits)})"
        if digits[0] in '01':
            return False, "Cannot start with 0 or 1"
        # Verhoeff checksum
        if not FieldValidator._verhoeff_check(digits):
            return False, "Verhoeff checksum failed"
        return True, None

    @staticmethod
    def _verhoeff_check(num_str: str) -> bool:
        """Verhoeff checksum validation for Aadhaar."""
        try:
            c = 0
            for i, digit in enumerate(reversed(num_str)):
                c = FieldValidator._VERHOEFF_D[c][FieldValidator._VERHOEFF_P[i % 8][int(digit)]]
            return c == 0
        except (IndexError, ValueError):
            return False

    @staticmethod
    def _validate_amount(value) -> Tuple[bool, Optional[str]]:
        try:
            val = float(value)
            if val <= 0:
                return False, "Must be positive"
            if val > 10_000_000:
                return False, "Exceeds ₹1,00,00,000 maximum"
            return True, None
        except (ValueError, TypeError):
            return False, "Not a valid number"

    @staticmethod
    def _validate_income(value) -> Tuple[bool, Optional[str]]:
        try:
            val = float(value)
            if val <= 0:
                return False, "Must be positive"
            return True, None
        except (ValueError, TypeError):
            return False, "Not a valid number"

    @staticmethod
    def _validate_land(value: str) -> Tuple[bool, Optional[str]]:
        if not value or len(str(value).strip()) < 1:
            return False, "Land details too short"
        return True, None

    @staticmethod
    def _validate_reason(value: str) -> Tuple[bool, Optional[str]]:
        if not value or len(str(value).strip()) < 3:
            return False, "Purpose too short"
        return True, None


# ═══════════════════════════════════════════════════════════════════════
#  STEP 5: CONFIDENCE SCORING
# ═══════════════════════════════════════════════════════════════════════

class ConfidenceScorer:
    """Per-field confidence scoring combining OCR confidence + validation + extraction method."""

    # Extraction method reliability weights
    METHOD_WEIGHTS = {
        "label_match": 0.8,
        "regex_pattern": 0.7,
        "regex_scan": 0.4,
        "llm_extract": 0.75,
        "not_found": 0.0,
    }

    @staticmethod
    def score_all(fields: Dict[str, Dict[str, Any]], ocr_avg_confidence: float) -> Dict[str, Dict[str, Any]]:
        """Compute final confidence for each field."""
        for key, field in fields.items():
            if field.get("value") is None:
                field["confidence"] = 0.0
                field["needs_review"] = True
                continue

            # Components
            ocr_conf = field.get("ocr_confidence", ocr_avg_confidence)
            method_weight = ConfidenceScorer.METHOD_WEIGHTS.get(
                field.get("method", "not_found"), 0.3
            )
            validation_bonus = 0.15 if field.get("validation_passed") else -0.2

            # Weighted combination
            confidence = (ocr_conf * 0.4) + (method_weight * 0.45) + (0.15 + validation_bonus)
            confidence = max(0.0, min(1.0, confidence))

            field["confidence"] = round(confidence, 2)
            field["needs_review"] = confidence < 0.6

        return fields


# ═══════════════════════════════════════════════════════════════════════
#  MAIN OCR SERVICE (orchestrator)
# ═══════════════════════════════════════════════════════════════════════

class OCRService:
    """Main orchestrator for the full OCR pipeline."""

    def __init__(self, fernet=None):
        self.fernet = fernet

    def process_document(self, image_bytes: bytes) -> Dict[str, Any]:
        """
        Full pipeline: preprocess → OCR → extract → validate → score.

        Three-engine strategy:
          1. LLaVA vision model (if Ollama available) — best for handwriting
          2. Region-aware Tesseract — per-field cropping with optimal PSM modes
          3. Full-page PaddleOCR/Tesseract + regex extraction — original pipeline

        Returns dict with:
          - fields: {field_name: {value, confidence, needs_review, ...}}
          - ocr_engine: which OCR engine was used
          - ocr_avg_confidence: average OCR confidence
          - full_text: raw OCR text
          - needs_review_fields: list of field names needing review
          - photo_box: {face_found, face_coords} if photo box detected
        """
        # Step 0: Photo box extraction (non-blocking)
        photo_box_result = None
        try:
            photo_box_result = FormRegionExtractor.extract_photo_box(image_bytes)
            if photo_box_result and photo_box_result.get("face_found"):
                logger.info("Face detected in form photo box")
        except Exception as e:
            logger.debug(f"Photo box extraction skipped: {e}")

        # Step 1: Preprocess
        try:
            preprocessed = ImagePreprocessor.preprocess(image_bytes)
            logger.info("Image preprocessing complete")
        except Exception as e:
            logger.error(f"Preprocessing failed: {e}")
            # Fallback: try raw image as numpy
            nparr = np.frombuffer(image_bytes, np.uint8)
            import cv2
            preprocessed = cv2.imdecode(nparr, cv2.IMREAD_GRAYSCALE)
            if preprocessed is None:
                return self._empty_result("Image decode failed")

        # Step 2: OCR
        ocr_result = TextRecognizer.recognize(preprocessed)
        logger.info(f"OCR engine: {ocr_result['engine']}, avg confidence: {ocr_result['avg_confidence']}")

        if not ocr_result["full_text"].strip():
            return self._empty_result("No text detected in document")

        # Step 3: Extract fields (regex + heuristic from full-page OCR)
        fields = FieldExtractor.extract(ocr_result)

        # Step 3b: Region-aware Tesseract enhancement
        try:
            region_results = FormRegionExtractor.run_per_field_ocr(image_bytes)
            if region_results:
                fields = self._merge_region_results(fields, region_results)
                logger.info(f"Region OCR merged {len(region_results)} fields")
        except Exception as e:
            logger.debug(f"Region OCR skipped: {e}")

        # Step 3c: LLaVA vision model enhancement (highest quality for handwriting)
        try:
            llm_result = LLMFieldExtractor.extract_with_vision(image_bytes)
            if llm_result:
                fields = self._merge_llm_results(fields, llm_result)
                logger.info("LLaVA vision extraction merged successfully")
            else:
                # Fallback to text-only LLM
                llm_text_result = LLMFieldExtractor.extract(ocr_result["full_text"])
                if llm_text_result:
                    fields = self._merge_llm_results(fields, llm_text_result)
                    logger.info("Ollama text extraction merged successfully")
        except Exception as e:
            logger.debug(f"LLM extraction skipped: {e}")

        # Step 4: Validate
        fields = FieldValidator.validate_all(fields)

        # Step 5: Confidence scoring
        fields = ConfidenceScorer.score_all(fields, ocr_result["avg_confidence"])

        # Compute needs_review list
        needs_review = [k for k, v in fields.items() if v.get("needs_review", True)]

        # Build clean output
        result = {
            "fields": {},
            "ocr_engine": ocr_result["engine"],
            "ocr_avg_confidence": ocr_result["avg_confidence"],
            "full_text": ocr_result["full_text"][:3000],  # Limit stored text
            "needs_review_fields": needs_review,
        }

        # Include photo box result
        if photo_box_result:
            result["photo_box"] = {
                "face_found": photo_box_result.get("face_found", False),
                "face_coords": photo_box_result.get("face_coords"),
            }

        for key, data in fields.items():
            result["fields"][key] = {
                "value": data.get("value"),
                "confidence": data.get("confidence", 0.0),
                "needs_review": data.get("needs_review", True),
                "validation_passed": data.get("validation_passed", False),
                "validation_error": data.get("validation_error"),
                "method": data.get("method", "not_found"),
            }

        return result

    def _merge_llm_results(self, regex_fields: Dict, llm_fields: Dict) -> Dict:
        """Merge LLM extraction into regex results, preferring higher-quality."""
        for key, llm_val in llm_fields.items():
            if key not in regex_fields:
                continue
            if llm_val is None:
                continue

            regex_data = regex_fields[key]
            # Use LLM value if regex didn't find anything or had low confidence
            if regex_data.get("value") is None or regex_data.get("method") == "not_found":
                regex_data["value"] = str(llm_val)
                regex_data["method"] = "llm_extract"
                regex_data["ocr_confidence"] = 0.6
            # Also use LLM if it appears higher quality (confidence < 0.5 from regex)
            elif regex_data.get("ocr_confidence", 0) < 0.5 and llm_val:
                regex_data["value"] = str(llm_val)
                regex_data["method"] = "llm_extract"
                regex_data["ocr_confidence"] = 0.65

        return regex_fields

    def _merge_region_results(self, fields: Dict, region_results: Dict) -> Dict:
        """Merge region-aware Tesseract results into existing fields.

        Region results are used when:
          - The full-page extraction missed the field entirely
          - The region result has higher confidence than the full-page result
        """
        for key, region_data in region_results.items():
            if key not in fields:
                continue
            if region_data.get("value") is None:
                continue

            existing = fields[key]
            region_conf = region_data.get("confidence", 0)
            existing_conf = existing.get("ocr_confidence", 0)

            # Use region result if existing field is empty or lower confidence
            if existing.get("value") is None or existing.get("method") == "not_found":
                fields[key] = region_data
            elif region_conf > existing_conf + 0.1:  # Require meaningful improvement
                fields[key] = region_data

        return fields

    def _empty_result(self, error_msg: str) -> Dict[str, Any]:
        """Return empty result structure."""
        empty_fields = {}
        for key in ["name", "account_number", "ifsc", "phone_number",
                     "aadhaar_number", "loan_amount", "annual_income",
                     "land_ownership", "loan_reason"]:
            empty_fields[key] = {
                "value": None,
                "confidence": 0.0,
                "needs_review": True,
                "validation_passed": False,
                "validation_error": error_msg,
                "method": "not_found",
            }
        return {
            "fields": empty_fields,
            "ocr_engine": "none",
            "ocr_avg_confidence": 0.0,
            "full_text": "",
            "needs_review_fields": list(empty_fields.keys()),
            "error": error_msg,
        }

    def mask_aadhaar(self, aadhaar: str) -> str:
        """Mask Aadhaar number: XXXX-XXXX-1234."""
        digits = re.sub(r'\D', '', str(aadhaar or ''))
        if len(digits) == 12:
            return f"XXXX-XXXX-{digits[-4:]}"
        return "XXXX-XXXX-****"

    def encrypt_fields(self, fields_dict: Dict) -> Optional[str]:
        """Encrypt all field data using Fernet."""
        if not self.fernet:
            return None
        try:
            data_bytes = json.dumps(fields_dict, default=str).encode()
            return self.fernet.encrypt(data_bytes).decode()
        except Exception as e:
            logger.error(f"Field encryption failed: {e}")
            return None
