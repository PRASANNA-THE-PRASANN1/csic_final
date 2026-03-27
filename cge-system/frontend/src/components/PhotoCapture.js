/**
 * PhotoCapture.js
 * Live photo capture component with face detection using face-api.js.
 * Used during farmer consent to prevent signature forgery (Fraud Type 3).
 *
 * Face detection runs every 500ms on the webcam stream.
 * The capture button is only enabled when a human face is detected.
 * If models fail to load, capture is still allowed with a warning.
 */
import React, { useRef, useState, useCallback, useEffect } from 'react';
import * as faceapi from 'face-api.js';

export default function PhotoCapture({ onCapture, required = false }) {
    const videoRef = useRef(null);
    const canvasRef = useRef(null);
    const detectionIntervalRef = useRef(null);
    const [stream, setStream] = useState(null);
    const [photo, setPhoto] = useState(null);
    const [error, setError] = useState('');
    const [cameraActive, setCameraActive] = useState(false);
    const [gpsLocation, setGpsLocation] = useState(null);
    const [modelsLoaded, setModelsLoaded] = useState(false);
    const [modelLoadFailed, setModelLoadFailed] = useState(false);
    const [faceDetected, setFaceDetected] = useState(false);
    const [faceConfidence, setFaceConfidence] = useState(0);
    const [loadingModels, setLoadingModels] = useState(true);

    // Get GPS location
    useEffect(() => {
        if (navigator.geolocation) {
            navigator.geolocation.getCurrentPosition(
                (position) => {
                    setGpsLocation({
                        latitude: position.coords.latitude,
                        longitude: position.coords.longitude,
                    });
                },
                () => {
                    setGpsLocation({ latitude: 19.0760, longitude: 72.8777 });
                }
            );
        } else {
            setGpsLocation({ latitude: 19.0760, longitude: 72.8777 });
        }
    }, []);

    // Load face-api.js models on mount
    useEffect(() => {
        let cancelled = false;
        const loadModels = async () => {
            setLoadingModels(true);
            try {
                const MODEL_URL = process.env.PUBLIC_URL + '/models';
                await faceapi.nets.tinyFaceDetector.loadFromUri(MODEL_URL);
                if (!cancelled) {
                    setModelsLoaded(true);
                    setModelLoadFailed(false);
                    console.log('✅ Face detection models loaded successfully');
                }
            } catch (err) {
                console.error('⚠ Failed to load face detection models:', err);
                if (!cancelled) {
                    setModelsLoaded(false);
                    setModelLoadFailed(true);
                }
            }
            if (!cancelled) setLoadingModels(false);
        };
        loadModels();

        return () => {
            cancelled = true;
            if (detectionIntervalRef.current) {
                clearInterval(detectionIntervalRef.current);
            }
        };
    }, []);

    // Start face detection loop when camera is active and models are loaded
    const startFaceDetection = useCallback(() => {
        if (!modelsLoaded || !videoRef.current) return;

        // Wait a moment for the video to actually start rendering frames
        setTimeout(() => {
            detectionIntervalRef.current = setInterval(async () => {
                const video = videoRef.current;
                if (!video || video.paused || video.ended || video.readyState < 2) return;

                try {
                    const detection = await faceapi.detectSingleFace(
                        video,
                        new faceapi.TinyFaceDetectorOptions({
                            inputSize: 224,
                            scoreThreshold: 0.4,
                        })
                    );

                    if (detection && detection.score > 0.5) {
                        setFaceDetected(true);
                        setFaceConfidence(Math.round(detection.score * 100));
                    } else {
                        setFaceDetected(false);
                        setFaceConfidence(detection ? Math.round(detection.score * 100) : 0);
                    }
                } catch (err) {
                    // Silently ignore detection errors during rapid polling
                    console.warn('Face detection poll error:', err);
                }
            }, 500);
        }, 1000); // Wait 1s for video to stabilize
    }, [modelsLoaded]);

    const startCamera = useCallback(async () => {
        try {
            setError('');
            const mediaStream = await navigator.mediaDevices.getUserMedia({
                video: { facingMode: 'user', width: { ideal: 480 }, height: { ideal: 360 } },
            });
            setStream(mediaStream);
            setCameraActive(true);
        } catch (err) {
            console.error('Camera access error:', err);
            setError('Camera access denied. Please allow camera access for identity verification.');
            setCameraActive(false);
        }
    }, []);

    // Assign stream to video element AFTER React renders it into the DOM.
    // The <video> is conditionally rendered only when cameraActive is true,
    // so videoRef.current is null inside startCamera. This effect runs after
    // the re-render that mounts the <video> element.
    useEffect(() => {
        if (!cameraActive || !stream || !videoRef.current) return;

        const video = videoRef.current;
        video.srcObject = stream;
        video.setAttribute('playsinline', true);

        video.play().then(() => {
            console.log('Video playing');
        }).catch((err) => {
            console.error('Play failed:', err);
        });

        video.onplaying = () => {
            if (modelsLoaded) {
                startFaceDetection();
            }
        };
    }, [cameraActive, stream, modelsLoaded, startFaceDetection]);

    const stopCamera = useCallback(() => {
        if (detectionIntervalRef.current) {
            clearInterval(detectionIntervalRef.current);
            detectionIntervalRef.current = null;
        }
        if (stream) {
            stream.getTracks().forEach((track) => track.stop());
            setStream(null);
        }
        setCameraActive(false);
        setFaceDetected(false);
        setFaceConfidence(0);
    }, [stream]);

    const capturePhoto = useCallback(() => {
        // If models loaded but no face detected, block capture
        if (modelsLoaded && !modelLoadFailed && !faceDetected) {
            setError('No face detected. Please look directly at the camera.');
            return;
        }

        const video = videoRef.current;
        const canvas = canvasRef.current;
        if (video && canvas) {
            canvas.width = video.videoWidth || 480;
            canvas.height = video.videoHeight || 360;
            const ctx = canvas.getContext('2d');
            ctx.drawImage(video, 0, 0);

            // Timestamp + face confidence overlay
            ctx.fillStyle = 'rgba(0, 0, 0, 0.5)';
            ctx.fillRect(0, canvas.height - 30, canvas.width, 30);
            ctx.fillStyle = '#fff';
            ctx.font = '12px monospace';
            const faceInfo = modelsLoaded ? `Face: ${faceConfidence}%` : 'Face detection N/A';
            ctx.fillText(
                `${new Date().toISOString()} | GPS: ${gpsLocation?.latitude?.toFixed(4)}, ${gpsLocation?.longitude?.toFixed(4)} | ${faceInfo}`,
                5,
                canvas.height - 10
            );

            const dataUrl = canvas.toDataURL('image/jpeg', 0.8);
            const base64 = dataUrl.split(',')[1];
            setPhoto(dataUrl);
            stopCamera();

            // Device fingerprint
            const deviceFingerprint = JSON.stringify({
                userAgent: navigator.userAgent,
                platform: navigator.platform,
                language: navigator.language,
                screenRes: `${screen.width}x${screen.height}`,
                timestamp: new Date().toISOString(),
                faceDetectionConfidence: faceConfidence,
            });

            if (onCapture) {
                onCapture({
                    photoBase64: base64,
                    gpsLatitude: gpsLocation?.latitude,
                    gpsLongitude: gpsLocation?.longitude,
                    deviceFingerprint,
                    faceDetectionConfidence: faceConfidence,
                });
            }
        }
    }, [gpsLocation, onCapture, stopCamera, faceDetected, faceConfidence, modelsLoaded, modelLoadFailed]);

    const retake = () => {
        setPhoto(null);
        setError('');
        if (onCapture) onCapture(null);
        startCamera();
    };

    // Can capture if: face detected OR if models failed to load (fallback mode)
    const canCapture = faceDetected || modelLoadFailed || !modelsLoaded;

    return (
        <div className="card p-3 mb-3">
            <h6>📸 Live Photo Verification {required && <span className="text-danger">*</span>}</h6>
            <p style={{ fontSize: '0.85em', color: '#666' }}>
                A live photo with face detection is captured during consent.
                {modelsLoaded && ' The system verifies a human face is present before allowing capture.'}
                {modelLoadFailed && ' (Face detection unavailable — capture still allowed)'}
            </p>

            {loadingModels && (
                <div style={{ padding: '8px 12px', background: 'rgba(100,216,255,0.08)', border: '1px solid rgba(100,216,255,0.2)', borderRadius: 8, marginBottom: 12, color: '#64d8ff', fontSize: '0.9em' }}>
                    🔄 Loading face detection models...
                </div>
            )}

            {error && (
                <div className="alert alert-warning" style={{ marginBottom: 12 }}>
                    {error}
                </div>
            )}

            {!photo && !cameraActive && !loadingModels && (
                <button className="btn btn-outline-primary" onClick={startCamera}>
                    📷 Open Camera
                </button>
            )}

            {cameraActive && (
                <div>
                    <video
                        ref={videoRef}
                        autoPlay
                        playsInline
                        muted
                        width="640"
                        height="480"
                        style={{
                            width: '100%',
                            maxWidth: 480,
                            borderRadius: 8,
                            border: `2px solid ${faceDetected ? '#28a745' : modelLoadFailed ? '#ffc107' : '#dc3545'}`,
                            transition: 'border-color 0.3s',
                        }}
                    />
                    {/* Face detection status indicator */}
                    {modelsLoaded && !modelLoadFailed && (
                        <div style={{
                            padding: '8px 12px',
                            marginTop: 8,
                            borderRadius: 8,
                            background: faceDetected ? 'rgba(40,167,69,0.1)' : 'rgba(220,53,69,0.1)',
                            border: `1px solid ${faceDetected ? '#28a745' : '#dc3545'}`,
                            fontSize: '0.9em',
                            fontWeight: 500,
                            color: faceDetected ? '#28a745' : '#dc3545',
                            transition: 'all 0.3s',
                        }}>
                            {faceDetected
                                ? `✅ Face detected (${faceConfidence}% confidence)`
                                : '❌ No face detected — please look directly at the camera'}
                        </div>
                    )}
                    {modelLoadFailed && (
                        <div style={{
                            padding: '8px 12px', marginTop: 8, borderRadius: 8,
                            background: 'rgba(255,193,7,0.1)', border: '1px solid #ffc107',
                            fontSize: '0.85em', color: '#ffc107',
                        }}>
                            ⚠ Face detection models unavailable. Capture is still allowed.
                        </div>
                    )}
                    <div className="mt-2">
                        <button
                            className="btn btn-success me-2"
                            onClick={capturePhoto}
                            disabled={!canCapture}
                            title={!canCapture ? 'A face must be detected before capture' : 'Capture photo'}
                        >
                            📸 Capture Photo
                        </button>
                        <button className="btn btn-outline-secondary" onClick={stopCamera}>
                            Cancel
                        </button>
                    </div>
                </div>
            )}

            {photo && (
                <div>
                    <img
                        src={photo}
                        alt="Captured"
                        style={{ width: '100%', maxWidth: 480, borderRadius: 8, border: '2px solid #28a745' }}
                    />
                    <div className="mt-2">
                        <span className="badge bg-success me-2">
                            ✅ Photo Captured {modelsLoaded && !modelLoadFailed ? '(Face verified)' : ''}
                        </span>
                        <button className="btn btn-sm btn-outline-primary" onClick={retake}>
                            🔄 Retake
                        </button>
                    </div>
                    {gpsLocation && (
                        <small className="text-muted d-block mt-1">
                            📍 GPS: {gpsLocation.latitude.toFixed(4)}, {gpsLocation.longitude.toFixed(4)}
                        </small>
                    )}
                </div>
            )}

            <canvas ref={canvasRef} style={{ display: 'none' }} />
        </div>
    );
}
