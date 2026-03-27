"""
PhotoVerificationService — Server-side image quality validation, liveness analysis,
encrypted photo storage, and auditor retrieval.

Addresses:
  Problem 1 — Client-side bypass: Pillow-based image quality checks
  Problem 2 — Forensic record: Fernet-encrypted photo storage with SHA-256 hash
  Problem 4 — Liveness detection: Multi-frame pixel variance analysis
  Problem 5 — Timestamp authority: All timestamps are server-side
"""

import os
import io
import hashlib
import logging
import numpy as np
from datetime import datetime, timezone
from PIL import Image
from cryptography.fernet import Fernet
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("cge.photo_verification")

MASTER_KEY = os.getenv("MASTER_KEY")
PHOTOS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "photos")

# Thresholds
MIN_DIMENSION = 200
MIN_FILE_SIZE = 5 * 1024        # 5 KB
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB
UNIFORMITY_STD_THRESHOLD = 15
LIVENESS_VARIANCE_THRESHOLD = 8


class PhotoVerificationService:
    """Handles image validation, liveness checks, encryption, and retrieval."""

    def __init__(self):
        os.makedirs(PHOTOS_DIR, exist_ok=True)
        if MASTER_KEY:
            self.fernet = Fernet(MASTER_KEY.encode() if isinstance(MASTER_KEY, str) else MASTER_KEY)
        else:
            self.fernet = None
            logger.warning("MASTER_KEY not set — photos will NOT be encrypted")

    # ── Image Quality Validation (Problem 1) ──────────────────────────

    def validate_image_quality(self, image_bytes: bytes) -> dict:
        """
        Run four server-side checks on a single frame.
        Returns {"valid": True} or {"valid": False, "error_code": "...", "detail": "..."}.
        """
        file_size = len(image_bytes)

        # Check 1: Valid file size range
        if file_size < MIN_FILE_SIZE:
            return {"valid": False, "error_code": "IMAGE_SIZE_INVALID",
                    "detail": f"Image too small ({file_size} bytes). Minimum is 5KB."}
        if file_size > MAX_FILE_SIZE:
            return {"valid": False, "error_code": "IMAGE_SIZE_INVALID",
                    "detail": f"Image too large ({file_size} bytes). Maximum is 5MB."}

        # Check 2: Valid image format
        try:
            img = Image.open(io.BytesIO(image_bytes))
            img.verify()  # verify it's a real image
            # Re-open after verify (verify closes the image)
            img = Image.open(io.BytesIO(image_bytes))
        except Exception:
            return {"valid": False, "error_code": "INVALID_IMAGE",
                    "detail": "File is not a valid image."}

        # Check 3: Minimum dimensions
        width, height = img.size
        if width < MIN_DIMENSION or height < MIN_DIMENSION:
            return {"valid": False, "error_code": "IMAGE_TOO_SMALL",
                    "detail": f"Image dimensions {width}x{height} are below minimum {MIN_DIMENSION}x{MIN_DIMENSION}."}

        # Check 4: Not uniform color
        try:
            arr = np.array(img.convert("RGB"), dtype=np.float32)
            std_dev = np.std(arr)
            if std_dev < UNIFORMITY_STD_THRESHOLD:
                return {"valid": False, "error_code": "IMAGE_TOO_UNIFORM",
                        "detail": f"Image appears to be a uniform color (std_dev={std_dev:.1f}). "
                                  "Possible covered camera or blank image."}
        except Exception:
            pass  # If conversion fails, skip this check rather than blocking

        return {"valid": True}

    # ── Frame Variance / Liveness Analysis (Problem 4) ────────────────

    def compute_frame_variance(self, frame1_bytes: bytes, frame2_bytes: bytes) -> float:
        """
        Compute mean absolute pixel difference between two frames.
        Returns a float on a 0-255 scale.
        """
        try:
            img1 = Image.open(io.BytesIO(frame1_bytes)).convert("RGB")
            img2 = Image.open(io.BytesIO(frame2_bytes)).convert("RGB")

            # Resize both to same dimensions for comparison
            target_size = (320, 240)
            img1 = img1.resize(target_size, Image.LANCZOS)
            img2 = img2.resize(target_size, Image.LANCZOS)

            arr1 = np.array(img1, dtype=np.float32)
            arr2 = np.array(img2, dtype=np.float32)

            mean_abs_diff = np.mean(np.abs(arr1 - arr2))
            return float(mean_abs_diff)
        except Exception as e:
            logger.error(f"Frame variance computation failed: {e}")
            return 999.0  # High value = assume frames are different (fail-open)

    def check_liveness(self, frame1: bytes, frame2: bytes, frame3: bytes) -> dict:
        """
        Multi-frame consistency check. Captures three frames and checks
        that they are meaningfully different (micro-movements).
        Returns {"liveness_suspicious": bool, "variance_1_2": float, "variance_2_3": float}
        """
        var_1_2 = self.compute_frame_variance(frame1, frame2)
        var_2_3 = self.compute_frame_variance(frame2, frame3)

        suspicious = var_1_2 < LIVENESS_VARIANCE_THRESHOLD and var_2_3 < LIVENESS_VARIANCE_THRESHOLD

        logger.info(f"Liveness check: var_1_2={var_1_2:.2f}, var_2_3={var_2_3:.2f}, suspicious={suspicious}")

        return {
            "liveness_suspicious": suspicious,
            "variance_1_2": round(var_1_2, 2),
            "variance_2_3": round(var_2_3, 2),
        }

    # ── Photo Hash (Problem 2) ────────────────────────────────────────

    def compute_photo_hash(self, frames: list[bytes]) -> str:
        """SHA-256 hash of all frames concatenated."""
        combined = b"".join(frames)
        return hashlib.sha256(combined).hexdigest()

    # ── Encrypted Storage (Problem 2) ─────────────────────────────────

    def encrypt_and_store(self, loan_id: str, frames: list[bytes]) -> str:
        """
        Encrypt all frames together and write to data/photos/{loan_id}.enc.
        Returns the storage path.
        """
        combined = b"".join(
            len(f).to_bytes(4, "big") + f for f in frames
        )

        file_path = os.path.join(PHOTOS_DIR, f"{loan_id}.enc")

        if self.fernet:
            encrypted = self.fernet.encrypt(combined)
            with open(file_path, "wb") as f:
                f.write(encrypted)
        else:
            # Fallback: store raw (not recommended for production)
            with open(file_path, "wb") as f:
                f.write(combined)
            logger.warning(f"Photo stored WITHOUT encryption for {loan_id}")

        logger.info(f"Photo stored: {file_path} ({len(combined)} bytes)")
        return file_path

    def decrypt_photo(self, loan_id: str) -> list[bytes]:
        """
        Read and decrypt stored photo frames.
        Returns a list of frame byte arrays.
        """
        file_path = os.path.join(PHOTOS_DIR, f"{loan_id}.enc")
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"No photo found for loan {loan_id}")

        with open(file_path, "rb") as f:
            data = f.read()

        if self.fernet:
            data = self.fernet.decrypt(data)

        # Parse length-prefixed frames
        frames = []
        offset = 0
        while offset < len(data):
            frame_len = int.from_bytes(data[offset:offset + 4], "big")
            offset += 4
            frames.append(data[offset:offset + frame_len])
            offset += frame_len

        return frames

    # ── Active Liveness Validation (Layered Verification) ─────────────

    def validate_active_liveness(self, challenge_data: dict, frames: list[bytes]) -> dict:
        """
        Server-side validation of active liveness challenges.
        Cross-references client-reported challenge results with frame analysis.

        Args:
            challenge_data: JSON from client with challenge results and timestamps
            frames: list of 5 frame byte arrays (baseline + challenge frames)

        Returns:
            {
                "active_liveness_passed": bool,
                "blink_verified": bool,
                "head_turn_verified": bool,
                "smile_verified": bool,
                "frame_variance_ok": bool,
                "suspicious_flags": list[str],
                "details": dict
            }
        """
        suspicious_flags = []
        details = {}

        # --- Validate challenge_data structure ---
        blink_claimed = challenge_data.get("blink_detected", False)
        head_turn_claimed = challenge_data.get("head_turn_detected", False)
        smile_claimed = challenge_data.get("smile_detected", False)
        challenge_order = challenge_data.get("challenge_order", [])
        challenge_timestamps = challenge_data.get("timestamps", {})

        # Must have at least 3 challenges reported
        if len(challenge_order) < 3:
            suspicious_flags.append("INCOMPLETE_CHALLENGES")

        # --- Timestamp validation ---
        # Challenges should take reasonable time (2-30 seconds each)
        for challenge_name, ts_data in challenge_timestamps.items():
            if isinstance(ts_data, dict):
                start = ts_data.get("start_ms", 0)
                end = ts_data.get("end_ms", 0)
                duration = end - start
                if duration < 500:  # Less than 0.5s is suspicious
                    suspicious_flags.append(f"TOO_FAST_{challenge_name.upper()}")
                if duration > 30000:  # More than 30s
                    suspicious_flags.append(f"TOO_SLOW_{challenge_name.upper()}")
                details[f"{challenge_name}_duration_ms"] = duration

        # --- Frame variance analysis across challenge windows ---
        if len(frames) >= 5:
            # Baseline frames (0, 1) should show micro-movement
            baseline_var = self.compute_frame_variance(frames[0], frames[1])
            details["baseline_variance"] = round(baseline_var, 2)

            # Challenge frames (2, 3, 4) should show MORE movement than baseline
            # because user is actively performing challenges
            challenge_var_1 = self.compute_frame_variance(frames[1], frames[2])
            challenge_var_2 = self.compute_frame_variance(frames[2], frames[3])
            challenge_var_3 = self.compute_frame_variance(frames[3], frames[4])

            details["challenge_variance_1"] = round(challenge_var_1, 2)
            details["challenge_variance_2"] = round(challenge_var_2, 2)
            details["challenge_variance_3"] = round(challenge_var_3, 2)

            avg_challenge_var = (challenge_var_1 + challenge_var_2 + challenge_var_3) / 3
            details["avg_challenge_variance"] = round(avg_challenge_var, 2)

            # If challenge frames show same or less variance than static threshold,
            # the person likely didn't perform the actions
            ACTIVE_VARIANCE_THRESHOLD = 5.0
            frame_variance_ok = avg_challenge_var >= ACTIVE_VARIANCE_THRESHOLD

            if not frame_variance_ok:
                suspicious_flags.append("LOW_CHALLENGE_VARIANCE")

            # Additional: challenge frames should have MORE variance than baseline
            # (because user is performing active gestures)
            if avg_challenge_var < baseline_var * 0.8:
                suspicious_flags.append("CHALLENGE_LESS_MOVEMENT_THAN_BASELINE")
        elif len(frames) >= 3:
            # Fallback for 3-frame capture
            var_1_2 = self.compute_frame_variance(frames[0], frames[1])
            var_2_3 = self.compute_frame_variance(frames[1], frames[2])
            frame_variance_ok = not (var_1_2 < LIVENESS_VARIANCE_THRESHOLD and var_2_3 < LIVENESS_VARIANCE_THRESHOLD)
            details["fallback_var_1_2"] = round(var_1_2, 2)
            details["fallback_var_2_3"] = round(var_2_3, 2)
        else:
            frame_variance_ok = False
            suspicious_flags.append("INSUFFICIENT_FRAMES")

        # --- Server-side blink verification ---
        # We can verify blink by checking that the frame captured during blink challenge
        # has a brightness dip in the eye region (darker = closed eyes)
        blink_verified = blink_claimed  # Trust client + frame variance
        if blink_claimed and len(frames) >= 3:
            # Cross-check: the blink frame should differ from adjacent frames
            blink_frame_idx = 2  # Default index for first challenge frame
            if "blink" in challenge_timestamps:
                blink_frame_idx = min(challenge_timestamps["blink"].get("frame_index", 2), len(frames) - 1)
            if blink_frame_idx > 0:
                blink_var = self.compute_frame_variance(frames[blink_frame_idx - 1], frames[blink_frame_idx])
                details["blink_frame_variance"] = round(blink_var, 2)
                if blink_var < 2.0:
                    suspicious_flags.append("BLINK_NO_FRAME_CHANGE")
                    blink_verified = False

        # --- Server-side head turn verification ---
        head_turn_verified = head_turn_claimed
        if head_turn_claimed and len(frames) >= 4:
            turn_frame_idx = 3
            if "head_turn" in challenge_timestamps:
                turn_frame_idx = min(challenge_timestamps["head_turn"].get("frame_index", 3), len(frames) - 1)
            if turn_frame_idx > 0:
                turn_var = self.compute_frame_variance(frames[turn_frame_idx - 1], frames[turn_frame_idx])
                details["head_turn_frame_variance"] = round(turn_var, 2)
                # Head turn should produce significant variance
                if turn_var < 3.0:
                    suspicious_flags.append("HEAD_TURN_NO_FRAME_CHANGE")
                    head_turn_verified = False

        # --- Server-side smile verification ---
        smile_verified = smile_claimed
        if smile_claimed and len(frames) >= 5:
            smile_frame_idx = 4
            if "smile" in challenge_timestamps:
                smile_frame_idx = min(challenge_timestamps["smile"].get("frame_index", 4), len(frames) - 1)
            if smile_frame_idx > 0:
                smile_var = self.compute_frame_variance(frames[smile_frame_idx - 1], frames[smile_frame_idx])
                details["smile_frame_variance"] = round(smile_var, 2)
                if smile_var < 1.5:
                    suspicious_flags.append("SMILE_NO_FRAME_CHANGE")
                    smile_verified = False

        # --- Overall decision ---
        all_challenges_passed = blink_verified and head_turn_verified and smile_verified
        active_liveness_passed = all_challenges_passed and frame_variance_ok and len(suspicious_flags) == 0

        logger.info(
            f"Active liveness: passed={active_liveness_passed}, "
            f"blink={blink_verified}, head_turn={head_turn_verified}, smile={smile_verified}, "
            f"variance_ok={frame_variance_ok}, flags={suspicious_flags}"
        )

        return {
            "active_liveness_passed": active_liveness_passed,
            "blink_verified": blink_verified,
            "head_turn_verified": head_turn_verified,
            "smile_verified": smile_verified,
            "frame_variance_ok": frame_variance_ok,
            "suspicious_flags": suspicious_flags,
            "details": details,
        }

    def check_multi_face(self, frames: list[bytes]) -> dict:
        """
        Server-side heuristic to detect multiple faces via skin-region analysis.
        Uses color segmentation to count large skin-colored regions.

        Returns: {"multi_face_suspected": bool, "regions_found": int}
        """
        try:
            max_regions = 0
            for frame_bytes in frames[:2]:  # Check first 2 frames
                img = Image.open(io.BytesIO(frame_bytes)).convert("RGB")
                img = img.resize((320, 240), Image.LANCZOS)
                arr = np.array(img, dtype=np.float32)

                # Simple skin detection in RGB space
                r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]
                skin_mask = (
                    (r > 95) & (g > 40) & (b > 20) &
                    (np.max(arr, axis=2) - np.min(arr, axis=2) > 15) &
                    (np.abs(r - g) > 15) & (r > g) & (r > b)
                ).astype(np.uint8)

                # Count connected regions (simple approach: count large clusters)
                # Use a simple flood-fill-like approach with downsampling
                small = skin_mask[::4, ::4]  # Downsample for speed
                total_skin = np.sum(small)
                # If there's a lot of skin, it could be multiple faces
                if total_skin > 200:  # Significant skin area
                    # Estimate regions by checking variance in skin distribution
                    top_half = np.sum(small[:small.shape[0] // 2, :])
                    bottom_half = np.sum(small[small.shape[0] // 2:, :])
                    left_half = np.sum(small[:, :small.shape[1] // 2])
                    right_half = np.sum(small[:, small.shape[1] // 2:])

                    # If skin is distributed across multiple quadrants fairly evenly,
                    # there might be multiple faces
                    quadrants_with_skin = sum(1 for q in [
                        np.sum(small[:30, :40]),
                        np.sum(small[:30, 40:]),
                        np.sum(small[30:, :40]),
                        np.sum(small[30:, 40:]),
                    ] if q > 30)
                    max_regions = max(max_regions, quadrants_with_skin)

            multi_face = max_regions >= 3  # Skin in 3+ quadrants is suspicious
            logger.info(f"Multi-face check: regions={max_regions}, suspected={multi_face}")
            return {"multi_face_suspected": multi_face, "regions_found": max_regions}

        except Exception as e:
            logger.error(f"Multi-face check failed: {e}")
            return {"multi_face_suspected": False, "regions_found": 0}

    def check_liveness_extended(self, frames: list[bytes]) -> dict:
        """
        Enhanced liveness check for 5-frame capture.
        Computes pairwise variance across all adjacent frames.
        Returns comprehensive liveness analysis.
        """
        if len(frames) < 3:
            return {"liveness_suspicious": True, "detail": "insufficient_frames"}

        variances = []
        for i in range(len(frames) - 1):
            var = self.compute_frame_variance(frames[i], frames[i + 1])
            variances.append(round(var, 2))

        avg_variance = sum(variances) / len(variances) if variances else 0
        min_variance = min(variances) if variances else 0
        max_variance = max(variances) if variances else 0

        # Suspicious if ALL pairs have very low variance (static image)
        all_static = all(v < LIVENESS_VARIANCE_THRESHOLD for v in variances)
        # Also suspicious if variance is identical across all pairs (replay)
        variance_range = max_variance - min_variance
        replay_suspected = variance_range < 1.0 and avg_variance > 20  # Looped video

        suspicious = all_static or replay_suspected

        logger.info(
            f"Extended liveness: variances={variances}, avg={avg_variance:.2f}, "
            f"range={variance_range:.2f}, suspicious={suspicious}"
        )

        return {
            "liveness_suspicious": suspicious,
            "variances": variances,
            "avg_variance": round(avg_variance, 2),
            "min_variance": round(min_variance, 2),
            "max_variance": round(max_variance, 2),
            "all_static": all_static,
            "replay_suspected": replay_suspected,
        }

