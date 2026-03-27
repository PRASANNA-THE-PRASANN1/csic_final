/**
 * KioskFaceMatch — Step 5: Face Match Verification (MOCK)
 * Currently simulates a successful face match.
 * Will be replaced with real camera-based comparison later.
 */

import React, { useState, useCallback, useEffect } from 'react';
import { useKiosk } from './KioskContext';

export default function KioskFaceMatch() {
    const { state, dispatch } = useKiosk();
    const [verifying, setVerifying] = useState(false);
    const [result, setResult] = useState(null);

    const aadhaarData = state.aadhaar_qr_data;
    const aadhaarName = aadhaarData?.name || 'Unknown';
    const aadhaarLast4 = aadhaarData?.aadhaar_last_four || '----';

    // Auto-advance after successful match
    useEffect(() => {
        if (result?.matched) {
            const timer = setTimeout(() => {
                dispatch({ type: 'NEXT_STEP' });
            }, 2000);
            return () => clearTimeout(timer);
        }
    }, [result, dispatch]);

    const handleVerify = useCallback(async () => {
        setVerifying(true);

        // Simulate processing time
        await new Promise(r => setTimeout(r, 1500));

        const mockResult = {
            matched: true,
            score: 0.87,
        };

        setResult(mockResult);

        dispatch({
            type: 'SET_FACE_MATCH',
            data: {
                score: mockResult.score,
                matched: mockResult.matched,
            },
        });

        // Also update the backend presence record with mock data
        try {
            const response = await fetch(
                `${process.env.REACT_APP_API_URL || 'http://localhost:8000'}/api/kiosk/${state.loanId}/face-match`,
                {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-Session-Token': state.sessionToken,
                    },
                    body: JSON.stringify({ simulated: true }),
                }
            );
            // We don't care if this fails — the mock result is already set
            if (!response.ok) {
                console.log('Mock face-match backend call returned non-200, ignoring for mock');
            }
        } catch (e) {
            console.log('Mock face-match backend call failed, ignoring for mock:', e.message);
        }

        setVerifying(false);
    }, [state.loanId, state.sessionToken, dispatch]);

    return (
        <div className="kiosk-step" id="kiosk-step-face-match">
            <div className="kiosk-step-header">
                <div className="kiosk-step-icon">🔍</div>
                <h2>Step 5: Face Match Verification</h2>
                <p>Comparing the Aadhaar photo with the live capture to verify identity.</p>
            </div>

            {/* Identity summary from Step 3 */}
            <div style={{
                background: 'linear-gradient(135deg, #eff6ff, #e0f2fe)',
                border: '1px solid #93c5fd',
                borderRadius: '12px',
                padding: '1.25rem',
                marginBottom: '1.5rem',
                maxWidth: '500px',
                margin: '0 auto 1.5rem',
            }}>
                <h3 style={{ margin: '0 0 0.75rem', color: '#1e40af', fontSize: '1rem' }}>
                    📋 Identity from Aadhaar QR
                </h3>
                <div style={{ display: 'grid', gap: '0.5rem', fontSize: '0.95rem' }}>
                    <div><strong>Name:</strong> {aadhaarName}</div>
                    <div><strong>Aadhaar:</strong> XXXX-XXXX-{aadhaarLast4}</div>
                </div>
            </div>

            {/* Demo mode badge */}
            <div style={{
                background: 'linear-gradient(135deg, #fef3c7, #fde68a)',
                border: '1px solid #f59e0b',
                borderRadius: '8px',
                padding: '0.75rem',
                textAlign: 'center',
                maxWidth: '500px',
                margin: '0 auto 1.5rem',
                fontSize: '0.85rem',
                color: '#92400e',
            }}>
                ⚠️ <strong>Demo Mode:</strong> Face match will be simulated. In production, a live camera photo will be compared server-side.
            </div>

            {/* Result display */}
            {result && (
                <div style={{
                    maxWidth: '500px',
                    margin: '0 auto 1.5rem',
                    padding: '1.5rem',
                    borderRadius: '12px',
                    border: '2px solid #10b981',
                    background: 'linear-gradient(135deg, #ecfdf5, #d1fae5)',
                    textAlign: 'center',
                }}>
                    <div style={{ fontSize: '3rem', marginBottom: '0.5rem' }}>✅</div>
                    <h3 style={{ color: '#059669', marginBottom: '0.5rem' }}>
                        Face Match Successful!
                    </h3>
                    <p style={{ color: '#64748b', fontSize: '0.9rem' }}>
                        Similarity Score: {Math.round((result.score || 0) * 100)}%
                    </p>
                    <p style={{ color: '#059669', fontWeight: '600', marginTop: '0.5rem' }}>
                        Advancing to next step...
                    </p>
                </div>
            )}

            {/* Action button */}
            {!result && (
                <div style={{ textAlign: 'center' }}>
                    <button
                        className="btn-kiosk-primary"
                        onClick={handleVerify}
                        disabled={verifying}
                        style={{ fontSize: '1.1rem', padding: '1rem 2.5rem' }}
                    >
                        {verifying ? (
                            <span>⏳ Verifying...</span>
                        ) : '🔍 Verify Identity (Simulated)'}
                    </button>
                </div>
            )}
        </div>
    );
}
