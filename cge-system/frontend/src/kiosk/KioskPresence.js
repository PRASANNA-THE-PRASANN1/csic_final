/**
 * KioskPresence — Layered Verification Model for secure presence capture.
 *
 * Layer 1: Face Detection (SSD MobileNet v1 — accurate)
 * Layer 2: Face Tracking + Framing Control (centering, size, eyes visible)
 * Layer 3: Auto-Capture (no manual button — system-controlled)
 * Layer 4: Active Liveness Challenges (blink twice, head turn, smile)
 *
 * Flow: GPS → Device Fingerprint → Camera Init → Model Loading →
 *       Face Tracking Loop → Framing Validation → Liveness Challenges →
 *       Auto-Capture 5 Frames → Upload → Cleanup
 */

import React, { useState, useEffect, useRef, useCallback } from 'react';
import * as faceapi from 'face-api.js';
import { useKiosk } from './KioskContext';
import { kioskCapturePhoto } from '../api';

// ── Helpers ──────────────────────────────────────────────────────────

async function sha256(text) {
    const encoder = new TextEncoder();
    const data = encoder.encode(text);
    const buffer = await crypto.subtle.digest('SHA-256', data);
    return Array.from(new Uint8Array(buffer)).map(b => b.toString(16).padStart(2, '0')).join('');
}

async function generateDeviceFingerprint() {
    const canvas = document.createElement('canvas');
    canvas.width = 200; canvas.height = 50;
    const ctx = canvas.getContext('2d');
    ctx.textBaseline = 'top';
    ctx.font = '16px Arial';
    ctx.fillStyle = '#f60';
    ctx.fillRect(125, 1, 62, 20);
    ctx.fillStyle = '#069';
    ctx.fillText('CGE Fingerprint', 2, 15);
    const canvasData = canvas.toDataURL();
    const canvasHash = await sha256(canvasData);

    let webglRenderer = 'unknown';
    try {
        const gl = document.createElement('canvas').getContext('webgl');
        if (gl) {
            const debugInfo = gl.getExtension('WEBGL_debug_renderer_info');
            if (debugInfo) webglRenderer = gl.getParameter(debugInfo.UNMASKED_RENDERER_WEBGL);
        }
    } catch (e) { /* ignore */ }

    const raw = `${canvasHash}|${webglRenderer}|${screen.width}x${screen.height}|${Intl.DateTimeFormat().resolvedOptions().timeZone}`;
    return await sha256(raw);
}

// ── Constants ────────────────────────────────────────────────────────

const FRAMING = {
    CENTER_TOLERANCE: 0.25,    // Face center within 25% of frame center
    MIN_FACE_RATIO: 0.12,     // Face width >= 12% of frame width
    MAX_FACE_RATIO: 0.55,     // Face width <= 55% of frame width
    EYE_OPEN_THRESHOLD: 0.22, // Eye aspect ratio threshold for "open"
    STABLE_DURATION: 2000,    // Face must be stable for 2 seconds
};

const CHALLENGE_TIMEOUT = 15000; // 15 seconds per challenge
const BLINK_EAR_THRESHOLD = 0.19; // Eye aspect ratio below this = blink
const SMILE_THRESHOLD = 0.65;     // Expression probability for smile
const HEAD_TURN_THRESHOLD = 0.12; // Nose offset ratio for head turn

// ── Eye Aspect Ratio (EAR) computation ──

function computeEAR(eyeLandmarks) {
    // Using 6-point eye model: p1..p6
    // EAR = (|p2-p6| + |p3-p5|) / (2 * |p1-p4|)
    if (!eyeLandmarks || eyeLandmarks.length < 6) return 0.3; // default open
    const p = eyeLandmarks;
    const dist = (a, b) => Math.sqrt((a.x - b.x) ** 2 + (a.y - b.y) ** 2);
    const vertical1 = dist(p[1], p[5]);
    const vertical2 = dist(p[2], p[4]);
    const horizontal = dist(p[0], p[3]);
    if (horizontal === 0) return 0.3;
    return (vertical1 + vertical2) / (2 * horizontal);
}

function getNoseOffset(landmarks, videoWidth) {
    // Compute nose tip horizontal offset from center as ratio
    if (!landmarks) return 0;
    const nose = landmarks.getNose();
    if (!nose || nose.length === 0) return 0;
    const noseTip = nose[3] || nose[0]; // tip of nose
    const centerX = videoWidth / 2;
    return (noseTip.x - centerX) / videoWidth;
}

// ── Component ────────────────────────────────────────────────────────

export default function KioskPresence() {
    const { state, dispatch } = useKiosk();

    // GPS
    const [gps, setGps] = useState(null);
    const [gpsError, setGpsError] = useState(null);
    const [gpsLoading, setGpsLoading] = useState(true);

    // Device fingerprint
    const [fingerprint, setFingerprint] = useState(null);

    // Camera & Models
    const [cameraReady, setCameraReady] = useState(false);
    const [cameraError, setCameraError] = useState(null);
    const [modelsLoaded, setModelsLoaded] = useState(false);
    const [modelsLoading, setModelsLoading] = useState(true);

    // Face Tracking (Layer 2)
    const [faceCount, setFaceCount] = useState(0);
    const [framingStatus, setFramingStatus] = useState({
        detected: false,
        centered: false,
        sizeOk: false,
        eyesVisible: false,
        allGood: false,
        message: 'Initializing camera...',
        messageHi: 'कैमरा शुरू हो रहा है...',
    });
    const [stableTimer, setStableTimer] = useState(0);

    // Liveness Challenges (Layer 4)
    const [challengePhase, setChallengePhase] = useState('tracking'); // tracking | challenging | capturing | done
    const [challenges, setChallenges] = useState([]);
    const [currentChallengeIdx, setCurrentChallengeIdx] = useState(0);
    const [challengeResults, setChallengeResults] = useState({});
    const [challengeTimer, setChallengeTimer] = useState(0);
    const [challengeTimestamps, setChallengeTimestamps] = useState({});

    // Capture
    const [capturedFrames, setCapturedFrames] = useState([]);
    const [framePreviewUrls, setFramePreviewUrls] = useState([]);
    const [countdownValue, setCountdownValue] = useState(0);

    // Upload
    const [uploading, setUploading] = useState(false);

    // Refs
    const videoRef = useRef(null);
    const canvasRef = useRef(null);
    const overlayRef = useRef(null);
    const streamRef = useRef(null);
    const detectionLoopRef = useRef(null);
    const stableStartRef = useRef(null);
    const challengeStartRef = useRef(null);
    const blinkCountRef = useRef(0);
    const blinkInProgressRef = useRef(false);
    const headTurnStateRef = useRef({ left: false, right: false, center: false });
    const lastLandmarksRef = useRef(null);
    const captureCanvasRef = useRef(null);
    const submittedRef = useRef(false);  // Guard against multiple submit/NEXT_STEP dispatches

    // ── Step 1: GPS ──────────────────────────────────────────────────

    useEffect(() => {
        if (!navigator.geolocation) {
            setGpsError('GPS not supported by this browser');
            setGpsLoading(false);
            return;
        }
        navigator.geolocation.getCurrentPosition(
            (pos) => {
                setGps({ lat: pos.coords.latitude, lng: pos.coords.longitude });
                setGpsLoading(false);
            },
            () => {
                setGpsError('Location access is required. Please allow location access. / स्थान की अनुमति आवश्यक है');
                setGpsLoading(false);
            },
            { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 }
        );
    }, []);

    // ── Step 2: Device Fingerprint ───────────────────────────────────

    useEffect(() => {
        if (gps) generateDeviceFingerprint().then(setFingerprint);
    }, [gps]);

    // ── Step 3: Load face-api models ─────────────────────────────────

    useEffect(() => {
        async function loadModels() {
            try {
                await Promise.all([
                    faceapi.nets.ssdMobilenetv1.loadFromUri('/models'),
                    faceapi.nets.faceLandmark68TinyNet.loadFromUri('/models'),
                    faceapi.nets.faceExpressionNet.loadFromUri('/models'),
                    faceapi.nets.tinyFaceDetector.loadFromUri('/models'),
                ]);
                setModelsLoaded(true);
            } catch (err) {
                console.error('Face model loading error:', err);
                // Fallback: try just tinyFaceDetector
                try {
                    await faceapi.nets.tinyFaceDetector.loadFromUri('/models');
                    setModelsLoaded(true);
                } catch (e2) {
                    console.error('All face models failed:', e2);
                }
            }
            setModelsLoading(false);
        }
        loadModels();
    }, []);

    // ── Step 4: Camera Init ──────────────────────────────────────────

    useEffect(() => {
        if (!gps || !fingerprint) return;
        async function initCamera() {
            try {
                const stream = await navigator.mediaDevices.getUserMedia({
                    video: { facingMode: 'user', width: { ideal: 1280 }, height: { ideal: 720 } }
                });
                streamRef.current = stream;
                if (videoRef.current) {
                    videoRef.current.srcObject = stream;
                    videoRef.current.play().catch(() => {});
                }
            } catch (err) {
                setCameraError('Camera access denied. Please allow camera. / कैमरा की अनुमति दें');
            }
        }
        initCamera();
        return () => {
            if (streamRef.current) streamRef.current.getTracks().forEach(t => t.stop());
            if (detectionLoopRef.current) cancelAnimationFrame(detectionLoopRef.current);
        };
    }, [gps, fingerprint]);

    // ── Step 5: Face Detection + Tracking Loop ──────────────────────

    const runDetectionLoop = useCallback(async () => {
        if (!videoRef.current || !modelsLoaded || challengePhase === 'done') return;

        const video = videoRef.current;
        if (video.paused || video.ended || video.readyState < 3) {
            detectionLoopRef.current = requestAnimationFrame(runDetectionLoop);
            return;
        }

        try {
            // Full detection with landmarks and expressions
            const detections = await faceapi
                .detectAllFaces(video, new faceapi.SsdMobilenetv1Options({ minConfidence: 0.5 }))
                .withFaceLandmarks(true)  // tiny landmarks
                .withFaceExpressions();

            const count = detections.length;
            setFaceCount(count);

            // Draw overlay
            drawOverlay(detections, video);

            if (count === 0) {
                updateFramingStatus(false, false, false, false,
                    '🔍 No face detected — look at the camera',
                    '🔍 कोई चेहरा नहीं दिखा — कैमरे की ओर देखें');
                stableStartRef.current = null;
                setStableTimer(0);
            } else if (count > 1) {
                updateFramingStatus(true, false, false, false,
                    `⚠️ ${count} faces detected — only 1 person should be in frame`,
                    `⚠️ ${count} चेहरे दिखे — केवल 1 व्यक्ति होना चाहिए`);
                stableStartRef.current = null;
                setStableTimer(0);
            } else {
                // Single face detected — check framing
                const det = detections[0];
                const box = det.detection.box;
                const vw = video.videoWidth;
                const vh = video.videoHeight;

                // Centering check
                const faceCenterX = (box.x + box.width / 2) / vw;
                const faceCenterY = (box.y + box.height / 2) / vh;
                const centered = Math.abs(faceCenterX - 0.5) < FRAMING.CENTER_TOLERANCE &&
                                 Math.abs(faceCenterY - 0.5) < FRAMING.CENTER_TOLERANCE;

                // Size check
                const faceRatio = box.width / vw;
                const sizeOk = faceRatio >= FRAMING.MIN_FACE_RATIO && faceRatio <= FRAMING.MAX_FACE_RATIO;

                // Eyes visible check via landmarks
                let eyesVisible = false;
                if (det.landmarks) {
                    const leftEye = det.landmarks.getLeftEye();
                    const rightEye = det.landmarks.getRightEye();
                    const leftEAR = computeEAR(leftEye);
                    const rightEAR = computeEAR(rightEye);
                    eyesVisible = leftEAR > FRAMING.EYE_OPEN_THRESHOLD && rightEAR > FRAMING.EYE_OPEN_THRESHOLD;

                    // Store for liveness challenges
                    lastLandmarksRef.current = {
                        landmarks: det.landmarks,
                        expressions: det.expressions,
                        leftEAR, rightEAR,
                        noseOffset: getNoseOffset(det.landmarks, vw),
                    };
                }

                const allGood = centered && sizeOk && eyesVisible;

                if (!centered) {
                    const msgs = [];
                    const msgsHi = [];
                    if (faceCenterX < 0.35) { msgs.push('Move right →'); msgsHi.push('दाएं जाएं →'); }
                    if (faceCenterX > 0.65) { msgs.push('← Move left'); msgsHi.push('← बाएं जाएं'); }
                    if (faceCenterY < 0.3) { msgs.push('Move down ↓'); msgsHi.push('नीचे जाएं ↓'); }
                    if (faceCenterY > 0.7) { msgs.push('Move up ↑'); msgsHi.push('ऊपर जाएं ↑'); }
                    updateFramingStatus(true, false, sizeOk, eyesVisible,
                        `📐 ${msgs.join(', ')}`, `📐 ${msgsHi.join(', ')}`);
                } else if (!sizeOk) {
                    const msg = faceRatio < FRAMING.MIN_FACE_RATIO ? 'Move closer to camera' : 'Move back from camera';
                    const msgHi = faceRatio < FRAMING.MIN_FACE_RATIO ? 'कैमरे के करीब आएं' : 'कैमरे से पीछे हटें';
                    updateFramingStatus(true, true, false, eyesVisible,
                        `📏 ${msg}`, `📏 ${msgHi}`);
                } else if (!eyesVisible) {
                    updateFramingStatus(true, true, true, false,
                        '👁️ Look directly at the camera, eyes open',
                        '👁️ सीधे कैमरे में देखें, आंखें खोलें');
                } else {
                    updateFramingStatus(true, true, true, true,
                        '✅ Perfect! Hold still...',
                        '✅ एकदम सही! रुकें...');
                }

                // Track stability timer
                if (allGood && challengePhase === 'tracking') {
                    if (!stableStartRef.current) {
                        stableStartRef.current = Date.now();
                    }
                    const elapsed = Date.now() - stableStartRef.current;
                    setStableTimer(Math.floor(elapsed / 1000));

                    if (elapsed >= FRAMING.STABLE_DURATION) {
                        // Face has been stable long enough — start challenges
                        startChallenges();
                    }
                } else if (!allGood) {
                    stableStartRef.current = null;
                    setStableTimer(0);
                }

                // Process active liveness challenges
                if (challengePhase === 'challenging' && det.landmarks && det.expressions) {
                    processChallenge(det);
                }
            }
        } catch (err) {
            // Silent detection error
        }

        if (challengePhase !== 'done') {
            detectionLoopRef.current = requestAnimationFrame(runDetectionLoop);
        }
    }, [modelsLoaded, challengePhase, challenges, currentChallengeIdx, challengeResults]);

    // Start detection loop when camera is ready
    useEffect(() => {
        if (cameraReady && modelsLoaded && challengePhase !== 'done') {
            detectionLoopRef.current = requestAnimationFrame(runDetectionLoop);
        }
        return () => {
            if (detectionLoopRef.current) cancelAnimationFrame(detectionLoopRef.current);
        };
    }, [cameraReady, modelsLoaded, runDetectionLoop, challengePhase]);

    // ── Overlay Drawing ──────────────────────────────────────────────

    function drawOverlay(detections, video) {
        const canvas = overlayRef.current;
        if (!canvas) return;

        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
        const ctx = canvas.getContext('2d');
        ctx.clearRect(0, 0, canvas.width, canvas.height);

        // Draw guide zone (center box)
        const guideX = canvas.width * 0.25;
        const guideY = canvas.height * 0.15;
        const guideW = canvas.width * 0.5;
        const guideH = canvas.height * 0.7;
        ctx.strokeStyle = 'rgba(255,255,255,0.3)';
        ctx.lineWidth = 2;
        ctx.setLineDash([10, 5]);
        ctx.strokeRect(guideX, guideY, guideW, guideH);
        ctx.setLineDash([]);

        detections.forEach(det => {
            const box = det.detection.box;
            const allGood = framingStatus.allGood;

            // Face bounding box
            ctx.strokeStyle = allGood ? '#00ff88' : '#ff4444';
            ctx.lineWidth = 3;
            ctx.strokeRect(box.x, box.y, box.width, box.height);

            // Corner accents
            const cornerLen = 20;
            ctx.lineWidth = 4;
            // Top-left
            ctx.beginPath(); ctx.moveTo(box.x, box.y + cornerLen); ctx.lineTo(box.x, box.y); ctx.lineTo(box.x + cornerLen, box.y); ctx.stroke();
            // Top-right
            ctx.beginPath(); ctx.moveTo(box.x + box.width - cornerLen, box.y); ctx.lineTo(box.x + box.width, box.y); ctx.lineTo(box.x + box.width, box.y + cornerLen); ctx.stroke();
            // Bottom-left
            ctx.beginPath(); ctx.moveTo(box.x, box.y + box.height - cornerLen); ctx.lineTo(box.x, box.y + box.height); ctx.lineTo(box.x + cornerLen, box.y + box.height); ctx.stroke();
            // Bottom-right
            ctx.beginPath(); ctx.moveTo(box.x + box.width - cornerLen, box.y + box.height); ctx.lineTo(box.x + box.width, box.y + box.height); ctx.lineTo(box.x + box.width, box.y + box.height - cornerLen); ctx.stroke();

            // Draw landmarks
            if (det.landmarks) {
                ctx.fillStyle = allGood ? 'rgba(0,255,136,0.5)' : 'rgba(255,200,0,0.5)';
                const positions = det.landmarks.positions;
                positions.forEach(p => {
                    ctx.beginPath();
                    ctx.arc(p.x, p.y, 2, 0, 2 * Math.PI);
                    ctx.fill();
                });
            }
        });

        // Countdown overlay
        if (countdownValue > 0) {
            ctx.fillStyle = 'rgba(0,0,0,0.4)';
            ctx.fillRect(0, 0, canvas.width, canvas.height);
            ctx.fillStyle = '#00ff88';
            ctx.font = `bold ${Math.floor(canvas.height * 0.3)}px Arial`;
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            ctx.fillText(countdownValue.toString(), canvas.width / 2, canvas.height / 2);
        }
    }

    // ── Framing Update Helper ────────────────────────────────────────

    function updateFramingStatus(detected, centered, sizeOk, eyesVisible, message, messageHi) {
        setFramingStatus({
            detected, centered, sizeOk, eyesVisible,
            allGood: detected && centered && sizeOk && eyesVisible,
            message, messageHi,
        });
    }

    // ── Liveness Challenges ──────────────────────────────────────────

    function startChallenges() {
        // Randomize challenge order
        const allChallenges = ['blink', 'head_turn', 'smile'];
        const shuffled = allChallenges.sort(() => Math.random() - 0.5);
        setChallenges(shuffled);
        setCurrentChallengeIdx(0);
        setChallengePhase('challenging');
        challengeStartRef.current = Date.now();
        blinkCountRef.current = 0;
        headTurnStateRef.current = { left: false, right: false, center: true };
        setChallengeTimestamps(prev => ({
            ...prev,
            [shuffled[0]]: { start_ms: Date.now() }
        }));
    }

    function processChallenge(detection) {
        if (currentChallengeIdx >= challenges.length) return;
        const currentChallenge = challenges[currentChallengeIdx];
        const landmarks = lastLandmarksRef.current;
        if (!landmarks) return;

        // Check timeout
        const elapsed = Date.now() - (challengeStartRef.current || Date.now());
        setChallengeTimer(Math.ceil((CHALLENGE_TIMEOUT - elapsed) / 1000));

        if (elapsed > CHALLENGE_TIMEOUT) {
            // Timeout — move to next challenge as failed
            advanceChallenge(currentChallenge, false);
            return;
        }

        switch (currentChallenge) {
            case 'blink': {
                const avgEAR = (landmarks.leftEAR + landmarks.rightEAR) / 2;
                if (avgEAR < BLINK_EAR_THRESHOLD) {
                    // Eyes closed
                    if (!blinkInProgressRef.current) {
                        blinkInProgressRef.current = true;
                    }
                } else {
                    // Eyes open — if was blinking, count it
                    if (blinkInProgressRef.current) {
                        blinkCountRef.current += 1;
                        blinkInProgressRef.current = false;
                    }
                }
                if (blinkCountRef.current >= 2) {
                    advanceChallenge('blink', true);
                }
                break;
            }
            case 'head_turn': {
                const offset = landmarks.noseOffset;
                if (offset < -HEAD_TURN_THRESHOLD) {
                    headTurnStateRef.current.left = true;
                } else if (offset > HEAD_TURN_THRESHOLD) {
                    headTurnStateRef.current.right = true;
                } else {
                    headTurnStateRef.current.center = true;
                }
                if (headTurnStateRef.current.left && headTurnStateRef.current.right) {
                    advanceChallenge('head_turn', true);
                }
                break;
            }
            case 'smile': {
                const expressions = detection.expressions;
                if (expressions && expressions.happy > SMILE_THRESHOLD) {
                    advanceChallenge('smile', true);
                }
                break;
            }
            default:
                break;
        }
    }

    function advanceChallenge(challengeName, passed) {
        // Capture a frame for this challenge
        captureFrameForChallenge(currentChallengeIdx + 2); // frames 2,3,4 are challenge frames

        const ts = { ...challengeTimestamps };
        if (ts[challengeName]) {
            ts[challengeName].end_ms = Date.now();
            ts[challengeName].frame_index = currentChallengeIdx + 2;
        }
        setChallengeTimestamps(ts);

        const newResults = { ...challengeResults, [challengeName]: passed };
        setChallengeResults(newResults);

        const nextIdx = currentChallengeIdx + 1;
        if (nextIdx < challenges.length) {
            setCurrentChallengeIdx(nextIdx);
            challengeStartRef.current = Date.now();
            blinkCountRef.current = 0;
            headTurnStateRef.current = { left: false, right: false, center: true };
            // Set start timestamp for next challenge
            setChallengeTimestamps(prev => ({
                ...prev,
                [challenges[nextIdx]]: { start_ms: Date.now() }
            }));
        } else {
            // All challenges done — auto-capture baseline frames
            // Guard: only fire once (rAF can call advanceChallenge multiple times before React re-renders)
            if (submittedRef.current) return;
            submittedRef.current = true;
            setChallengePhase('capturing');
            performAutoCapture(newResults, ts);
        }
    }

    // ── Frame Capture ────────────────────────────────────────────────

    const challengeFramesRef = useRef([]);

    function captureFrameForChallenge(frameIdx) {
        if (!videoRef.current) return;
        const canvas = captureCanvasRef.current || document.createElement('canvas');
        if (!captureCanvasRef.current) captureCanvasRef.current = canvas;

        canvas.width = videoRef.current.videoWidth || 640;
        canvas.height = videoRef.current.videoHeight || 480;
        const ctx = canvas.getContext('2d');
        ctx.drawImage(videoRef.current, 0, 0, canvas.width, canvas.height);

        canvas.toBlob((blob) => {
            if (blob) {
                challengeFramesRef.current[frameIdx] = blob;
            }
        }, 'image/jpeg', 0.85);
    }

    async function performAutoCapture(results, timestamps) {
        if (!videoRef.current || videoRef.current.readyState < 2) return;

        const canvas = captureCanvasRef.current || document.createElement('canvas');
        if (!captureCanvasRef.current) captureCanvasRef.current = canvas;
        canvas.width = videoRef.current.videoWidth || 640;
        canvas.height = videoRef.current.videoHeight || 480;
        const ctx = canvas.getContext('2d');

        const allFrames = [];
        const previews = [];

        // Countdown 3-2-1
        for (let c = 3; c >= 1; c--) {
            setCountdownValue(c);
            await new Promise(r => setTimeout(r, 800));
        }
        setCountdownValue(0);

        // Capture 2 baseline frames
        for (let i = 0; i < 2; i++) {
            if (i > 0) await new Promise(r => setTimeout(r, 500));
            const video = videoRef.current;
            if (!video || video.readyState < 2) break;
            ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
            const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/jpeg', 0.85));
            allFrames.push(blob);
            previews.push(URL.createObjectURL(blob));
        }

        // Add challenge frames (captured during challenges)
        for (let i = 2; i < 5; i++) {
            const challengeFrame = challengeFramesRef.current[i];
            if (challengeFrame) {
                allFrames.push(challengeFrame);
                previews.push(URL.createObjectURL(challengeFrame));
            } else {
                // Fallback — capture now
                const fallbackVideo = videoRef.current;
                if (!fallbackVideo || fallbackVideo.readyState < 2) continue;
                ctx.drawImage(fallbackVideo, 0, 0, canvas.width, canvas.height);
                const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/jpeg', 0.85));
                allFrames.push(blob);
                previews.push(URL.createObjectURL(blob));
            }
        }

        setCapturedFrames(allFrames);
        setFramePreviewUrls(previews);
        setChallengePhase('done');

        // Stop detection
        if (detectionLoopRef.current) cancelAnimationFrame(detectionLoopRef.current);

        // Auto-submit
        await handleSubmit(allFrames, results, timestamps);
    }

    // ── Upload ───────────────────────────────────────────────────────

    const handleSubmit = async (frames, results, timestamps) => {
        if (!frames || frames.length < 3) return;
        setUploading(true);
        dispatch({ type: 'SET_ERROR', error: null });

        try {
            const formData = new FormData();
            formData.append('frame_1', frames[0], 'frame_1.jpg');
            formData.append('frame_2', frames[1], 'frame_2.jpg');
            formData.append('frame_3', frames[2], 'frame_3.jpg');
            if (frames[3]) formData.append('frame_4', frames[3], 'frame_4.jpg');
            if (frames[4]) formData.append('frame_5', frames[4], 'frame_5.jpg');
            formData.append('gps_latitude', gps.lat.toString());
            formData.append('gps_longitude', gps.lng.toString());
            formData.append('device_fingerprint', fingerprint);
            formData.append('face_detected_client_side', 'true');
            formData.append('face_count_client', faceCount.toString());
            formData.append('face_centered', framingStatus.centered ? 'true' : 'false');
            formData.append('auto_captured', 'true');

            // Liveness challenge data
            const challengeData = {
                blink_detected: results?.blink || false,
                head_turn_detected: results?.head_turn || false,
                smile_detected: results?.smile || false,
                challenge_order: challenges,
                timestamps: timestamps || {},
            };
            formData.append('liveness_challenges_json', JSON.stringify(challengeData));

            const res = await kioskCapturePhoto(state.loanId, formData, state.sessionToken);

            dispatch({
                type: 'SET_PRESENCE_DATA',
                photoHash: res.data.photo_hash,
                livenessSuspicious: res.data.liveness_check_suspicious,
                activeLiveness: res.data.active_liveness_passed,
            });

            // Cleanup camera
            if (streamRef.current) {
                streamRef.current.getTracks().forEach(t => t.stop());
            }

            dispatch({ type: 'NEXT_STEP' });
        } catch (err) {
            const msg = err.response?.data?.detail || 'Failed to submit presence data';
            dispatch({ type: 'SET_ERROR', error: typeof msg === 'object' ? msg.message : msg });
            // Allow retry
            submittedRef.current = false;  // Reset guard on error to allow retry
            setChallengePhase('tracking');
            setCapturedFrames([]);
            framePreviewUrls.forEach(url => URL.revokeObjectURL(url));
            setFramePreviewUrls([]);
            setChallengeResults({});
            challengeFramesRef.current = [];
            stableStartRef.current = null;
        } finally {
            setUploading(false);
        }
    };

    // Cleanup preview URLs on unmount
    useEffect(() => {
        return () => {
            framePreviewUrls.forEach(url => URL.revokeObjectURL(url));
        };
    }, [framePreviewUrls]);

    // Camera ready handler
    const handleVideoPlaying = useCallback(() => {
        setCameraReady(true);
    }, []);

    // ── Challenge Display Info ───────────────────────────────────────

    function getChallengeInfo(challenge) {
        switch (challenge) {
            case 'blink':
                return {
                    icon: '👁️',
                    title: 'Blink Twice',
                    titleHi: 'दो बार पलकें झपकाएं',
                    description: 'Please blink your eyes twice slowly',
                    descHi: 'कृपया अपनी आँखें दो बार धीरे से झपकाएं',
                };
            case 'head_turn':
                return {
                    icon: '↔️',
                    title: 'Turn Your Head',
                    titleHi: 'सिर घुमाएं',
                    description: 'Slowly turn your head left then right',
                    descHi: 'धीरे-धीरे सिर बाएं फिर दाएं घुमाएं',
                };
            case 'smile':
                return {
                    icon: '😊',
                    title: 'Smile',
                    titleHi: 'मुस्कुराएं',
                    description: 'Please smile naturally at the camera',
                    descHi: 'कृपया कैमरे को देखकर स्वाभाविक रूप से मुस्कुराएं',
                };
            default:
                return { icon: '❓', title: '', titleHi: '', description: '', descHi: '' };
        }
    }

    // ── Render ────────────────────────────────────────────────────────

    return (
        <div className="kiosk-step kiosk-presence">
            <h2 className="kiosk-step-title">🔐 Secure Presence Verification</h2>
            <p className="kiosk-step-subtitle">
                Advanced identity verification with live camera checks.
                <br />
                <span className="kiosk-hindi">उन्नत पहचान सत्यापन — लाइव कैमरा जांच</span>
            </p>

            {/* GPS Error */}
            {gpsError && !gps && (
                <div className="kiosk-error-banner">
                    <span>⚠️</span> {gpsError}
                </div>
            )}

            {gps && (
                <div className="kiosk-presence-grid">
                    {/* Main Camera Card */}
                    <div className="kiosk-card kiosk-camera-card">
                        <h3>📷 Live Verification Camera</h3>

                        {cameraError ? (
                            <div className="kiosk-error-banner">
                                <span>⚠️</span> {cameraError}
                            </div>
                        ) : (
                            <>
                                {/* Camera with overlay */}
                                <div className="kiosk-camera-preview" style={{ position: 'relative' }}>
                                    {challengePhase !== 'done' ? (
                                        <>
                                            <video
                                                ref={videoRef}
                                                autoPlay
                                                muted
                                                playsInline
                                                width={640}
                                                height={480}
                                                onPlaying={handleVideoPlaying}
                                                className="kiosk-video-feed"
                                                style={{ transform: 'scaleX(-1)' }}
                                            />
                                            <canvas
                                                ref={overlayRef}
                                                className="kiosk-overlay-canvas"
                                                style={{
                                                    position: 'absolute',
                                                    top: 0, left: 0,
                                                    width: '100%', height: '100%',
                                                    pointerEvents: 'none',
                                                    transform: 'scaleX(-1)',
                                                }}
                                            />
                                        </>
                                    ) : (
                                        <div className="kiosk-frame-previews">
                                            {framePreviewUrls.slice(0, 3).map((url, i) => (
                                                <div key={i} className="kiosk-frame-preview">
                                                    <img src={url} alt={`Frame ${i + 1}`} />
                                                    <span>{i < 2 ? `Baseline ${i + 1}` : 'Challenge'}</span>
                                                </div>
                                            ))}
                                        </div>
                                    )}
                                </div>

                                {/* Models loading */}
                                {modelsLoading && (
                                    <div className="kiosk-face-status detecting">
                                        ⏳ Loading AI models... Please wait
                                    </div>
                                )}

                                {/* Layer-by-layer verification status */}
                                {cameraReady && modelsLoaded && challengePhase !== 'done' && (
                                    <div className="kiosk-verification-layers">
                                        {/* Framing Status */}
                                        <div className={`kiosk-layer-status ${framingStatus.allGood ? 'success' : 'active'}`}>
                                            <div className="kiosk-layer-header">
                                                <span className="kiosk-layer-icon">📐</span>
                                                <span className="kiosk-layer-title">Face Framing</span>
                                            </div>
                                            <div className="kiosk-layer-checks">
                                                <span className={framingStatus.detected ? 'check-pass' : 'check-fail'}>
                                                    {framingStatus.detected ? '✅' : '⬜'} Face Detected
                                                </span>
                                                <span className={framingStatus.centered ? 'check-pass' : 'check-fail'}>
                                                    {framingStatus.centered ? '✅' : '⬜'} Centered
                                                </span>
                                                <span className={framingStatus.sizeOk ? 'check-pass' : 'check-fail'}>
                                                    {framingStatus.sizeOk ? '✅' : '⬜'} Proper Size
                                                </span>
                                                <span className={framingStatus.eyesVisible ? 'check-pass' : 'check-fail'}>
                                                    {framingStatus.eyesVisible ? '✅' : '⬜'} Eyes Visible
                                                </span>
                                            </div>
                                            <div className="kiosk-framing-message">
                                                {framingStatus.message}
                                                <br />
                                                <span className="kiosk-hindi">{framingStatus.messageHi}</span>
                                            </div>
                                        </div>

                                        {/* Stability countdown */}
                                        {framingStatus.allGood && challengePhase === 'tracking' && (
                                            <div className="kiosk-stable-countdown">
                                                <div className="kiosk-stable-bar">
                                                    <div
                                                        className="kiosk-stable-fill"
                                                        style={{ width: `${Math.min(100, (stableTimer / (FRAMING.STABLE_DURATION / 1000)) * 100)}%` }}
                                                    />
                                                </div>
                                                <span>Hold still... {stableTimer}s / {FRAMING.STABLE_DURATION / 1000}s</span>
                                            </div>
                                        )}

                                        {/* Liveness Challenges */}
                                        {challengePhase === 'challenging' && challenges.length > 0 && (
                                            <div className="kiosk-challenge-section">
                                                <div className="kiosk-layer-header">
                                                    <span className="kiosk-layer-icon">🔐</span>
                                                    <span className="kiosk-layer-title">Active Liveness Check</span>
                                                </div>

                                                {/* Challenge progress */}
                                                <div className="kiosk-challenge-progress">
                                                    {challenges.map((ch, idx) => (
                                                        <div
                                                            key={ch}
                                                            className={`kiosk-challenge-dot ${
                                                                idx < currentChallengeIdx ? 'completed' :
                                                                idx === currentChallengeIdx ? 'active' : 'pending'
                                                            } ${challengeResults[ch] === false ? 'failed' : ''}`}
                                                        >
                                                            {idx < currentChallengeIdx ? (
                                                                challengeResults[ch] ? '✅' : '❌'
                                                            ) : idx === currentChallengeIdx ? (
                                                                getChallengeInfo(ch).icon
                                                            ) : (
                                                                '⬜'
                                                            )}
                                                        </div>
                                                    ))}
                                                </div>

                                                {/* Current challenge instruction */}
                                                {currentChallengeIdx < challenges.length && (
                                                    <div className="kiosk-challenge-card">
                                                        <div className="kiosk-challenge-icon">
                                                            {getChallengeInfo(challenges[currentChallengeIdx]).icon}
                                                        </div>
                                                        <div className="kiosk-challenge-text">
                                                            <strong>{getChallengeInfo(challenges[currentChallengeIdx]).title}</strong>
                                                            <br />
                                                            {getChallengeInfo(challenges[currentChallengeIdx]).description}
                                                            <br />
                                                            <span className="kiosk-hindi">
                                                                {getChallengeInfo(challenges[currentChallengeIdx]).descHi}
                                                            </span>
                                                        </div>
                                                        <div className="kiosk-challenge-timer">
                                                            ⏱ {challengeTimer}s
                                                        </div>
                                                    </div>
                                                )}
                                            </div>
                                        )}

                                        {/* Capturing */}
                                        {challengePhase === 'capturing' && (
                                            <div className="kiosk-face-status detecting">
                                                📸 Auto-capturing verification frames...
                                            </div>
                                        )}
                                    </div>
                                )}

                                {/* Upload status */}
                                {uploading && (
                                    <div className="kiosk-face-status detecting">
                                        ⏳ Verifying & uploading to secure server...
                                    </div>
                                )}

                                {/* Done status */}
                                {challengePhase === 'done' && !uploading && (
                                    <div className="kiosk-face-status success">
                                        ✅ Verification complete — all checks passed
                                    </div>
                                )}
                            </>
                        )}
                    </div>

                    {/* Info Sidebar */}
                    <div className="kiosk-card">
                        <h3>📋 Verification Status</h3>
                        <div className="kiosk-verification-checklist">
                            <div className={`kiosk-checklist-item ${gps ? 'done' : ''}`}>
                                {gps ? '✅' : '⬜'} GPS Location Captured
                                {gps && (
                                    <div className="kiosk-gps-coords" style={{ fontSize: '0.8rem', opacity: 0.7 }}>
                                        Lat: {gps.lat.toFixed(4)}, Lng: {gps.lng.toFixed(4)}
                                    </div>
                                )}
                            </div>
                            <div className={`kiosk-checklist-item ${fingerprint ? 'done' : ''}`}>
                                {fingerprint ? '✅' : '⬜'} Device Fingerprint
                            </div>
                            <div className={`kiosk-checklist-item ${framingStatus.allGood ? 'done' : ''}`}>
                                {framingStatus.allGood ? '✅' : '⬜'} Face Properly Framed
                            </div>
                            <div className={`kiosk-checklist-item ${challengeResults.blink ? 'done' : ''}`}>
                                {challengeResults.blink ? '✅' : '⬜'} Blink Detection
                            </div>
                            <div className={`kiosk-checklist-item ${challengeResults.head_turn ? 'done' : ''}`}>
                                {challengeResults.head_turn ? '✅' : '⬜'} Head Turn Detection
                            </div>
                            <div className={`kiosk-checklist-item ${challengeResults.smile ? 'done' : ''}`}>
                                {challengeResults.smile ? '✅' : '⬜'} Smile Detection
                            </div>
                            <div className={`kiosk-checklist-item ${capturedFrames.length >= 3 ? 'done' : ''}`}>
                                {capturedFrames.length >= 3 ? '✅' : '⬜'} Photos Auto-Captured ({capturedFrames.length}/5)
                            </div>
                        </div>

                        {/* Security note */}
                        <div className="kiosk-security-note" style={{
                            marginTop: '1rem', padding: '0.8rem',
                            background: 'rgba(255,255,255,0.05)',
                            borderRadius: '8px', fontSize: '0.8rem',
                            lineHeight: 1.5, opacity: 0.7,
                        }}>
                            🔒 <strong>Security Info:</strong> This system uses AI-powered face tracking,
                            active liveness detection, and server-side validation. Photos are encrypted
                            and stored with SHA-256 hash verification.
                            <br />
                            <span className="kiosk-hindi">
                                🔒 यह सिस्टम AI-संचालित चेहरा ट्रैकिंग और लाइवनेस जांच का उपयोग करता है।
                            </span>
                        </div>
                    </div>
                </div>
            )}

            {/* Hidden canvas for frame capture */}
            <canvas ref={canvasRef} style={{ display: 'none' }} />

            {/* Assigned Employee Banner */}
            {challengePhase === 'done' && state.employeeName && (
                <div className="kiosk-employee-section">
                    <div className="kiosk-employee-assigned-banner">
                        <span className="kiosk-employee-assigned-icon">👨‍💼</span>
                        <div className="kiosk-employee-assigned-info">
                            <strong>Assigned Employee / सौंपा गया कर्मचारी</strong>
                            <span>👤 {state.employeeName} ({state.employeeId})</span>
                        </div>
                        <span className="kiosk-employee-verified-badge">✅ Registered</span>
                    </div>
                    <div className="kiosk-employee-note">
                        ℹ️ This employee was assigned at session start and is recorded immutably.
                    </div>
                </div>
            )}
        </div>
    );
}
