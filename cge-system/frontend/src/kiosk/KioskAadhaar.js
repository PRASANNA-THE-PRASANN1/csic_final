/**
 * KioskAadhaar — Step 6: Aadhaar OTP verification.
 * Pre-fills Aadhaar last 4 digits from QR scan (Step 3).
 * Farmer only enters mobile last 4 digits.
 * OTP is displayed on-screen for the demo (production: SMS only).
 */

import React, { useState } from 'react';
import { useKiosk } from './KioskContext';
import { kioskAadhaarInitiate, kioskAadhaarVerify } from '../api';

export default function KioskAadhaar() {
    const { state, dispatch } = useKiosk();
    const [phase, setPhase] = useState('input'); // 'input' | 'otp' | 'verified'

    // Pre-fill from QR scan data
    const qrData = state.aadhaar_qr_data;
    const [aadhaarLast4] = useState(qrData?.aadhaar_last_four || '');
    const [mobileLast4, setMobileLast4] = useState('');
    const [otp, setOtp] = useState('');
    const [otpRefId, setOtpRefId] = useState('');
    const [otpDisplay, setOtpDisplay] = useState('');
    const [loading, setLoading] = useState(false);
    const [verifiedName, setVerifiedName] = useState(qrData?.name || '');

    const handleInitiate = async () => {
        if (aadhaarLast4.length !== 4 || mobileLast4.length !== 4) {
            dispatch({ type: 'SET_ERROR', error: 'Please enter exactly 4 digits for both fields.' });
            return;
        }
        setLoading(true);
        dispatch({ type: 'SET_ERROR', error: null });
        try {
            const res = await kioskAadhaarInitiate(state.loanId, {
                aadhaar_last_four: aadhaarLast4,
                mobile_last_four: mobileLast4,
            }, state.sessionToken);
            setOtpRefId(res.data.otp_reference_id);
            // Display OTP on screen (demo only — production uses SMS via UIDAI)
            if (res.data.otp_display) {
                setOtpDisplay(res.data.otp_display);
            }
            setPhase('otp');
        } catch (err) {
            const msg = err.response?.data?.detail || 'Failed to initiate Aadhaar verification';
            dispatch({ type: 'SET_ERROR', error: typeof msg === 'object' ? msg.message : msg });
        } finally {
            setLoading(false);
        }
    };

    const handleVerify = async () => {
        if (otp.length < 4) {
            dispatch({ type: 'SET_ERROR', error: 'Please enter the complete OTP.' });
            return;
        }
        setLoading(true);
        dispatch({ type: 'SET_ERROR', error: null });
        try {
            const res = await kioskAadhaarVerify(state.loanId, {
                otp_reference_id: otpRefId,
                otp: otp,
            }, state.sessionToken);
            setVerifiedName(res.data.verified_name || res.data.aadhaar_verified_name || verifiedName);
            dispatch({ type: 'SET_FARMER', name: res.data.verified_name || res.data.aadhaar_verified_name || verifiedName });
            setPhase('verified');
        } catch (err) {
            const msg = err.response?.data?.detail || 'OTP verification failed';
            dispatch({ type: 'SET_ERROR', error: typeof msg === 'object' ? msg.message : msg });
        } finally {
            setLoading(false);
        }
    };

    if (phase === 'verified') {
        return (
            <div className="kiosk-step kiosk-aadhaar">
                <h2 className="kiosk-step-title">✅ Identity Verified</h2>
                <div className="kiosk-verified-card">
                    <div className="kiosk-verified-icon">🪪</div>
                    <div className="kiosk-verified-details">
                        <div className="kiosk-verified-name">{verifiedName}</div>
                        <div className="kiosk-verified-aadhaar">
                            Aadhaar: XXXX-XXXX-{aadhaarLast4}
                        </div>
                        <div className="kiosk-verified-badge">
                            ✅ Aadhaar OTP Verified
                        </div>
                    </div>
                </div>
                <button
                    className="btn-kiosk-primary"
                    onClick={() => dispatch({ type: 'NEXT_STEP' })}
                >
                    → Continue to Document Upload
                </button>
            </div>
        );
    }

    return (
        <div className="kiosk-step kiosk-aadhaar">
            <h2 className="kiosk-step-title">🪪 Step 6: Aadhaar OTP Verification</h2>
            <p className="kiosk-step-subtitle">
                Verify identity using OTP sent to Aadhaar-linked mobile number
            </p>

            {/* Show pre-filled identity from QR */}
            {qrData && (
                <div style={{
                    background: 'linear-gradient(135deg, #f0fdf4, #ecfdf5)',
                    border: '1px solid #86efac',
                    borderRadius: '10px',
                    padding: '1rem',
                    marginBottom: '1.25rem',
                    fontSize: '0.9rem',
                }}>
                    <strong>📋 From QR Scan:</strong> {qrData.name} — XXXX-XXXX-{qrData.aadhaar_last_four}
                </div>
            )}

            {phase === 'input' && (
                <div className="kiosk-form">
                    <div className="kiosk-form-group">
                        <label>Last 4 digits of Aadhaar Number</label>
                        <input
                            type="text"
                            maxLength={4}
                            pattern="[0-9]*"
                            inputMode="numeric"
                            value={aadhaarLast4}
                            readOnly
                            className="kiosk-input kiosk-input-otp"
                            style={{
                                backgroundColor: '#f1f5f9',
                                cursor: 'not-allowed',
                                color: '#475569',
                                fontWeight: '600',
                            }}
                        />
                        {qrData && (
                            <span style={{ fontSize: '0.8rem', color: '#64748b' }}>
                                🔒 Pre-filled from QR scan (read-only)
                            </span>
                        )}
                    </div>
                    <div className="kiosk-form-group">
                        <label>Last 4 digits of Registered Mobile</label>
                        <input
                            type="text"
                            maxLength={4}
                            pattern="[0-9]*"
                            inputMode="numeric"
                            value={mobileLast4}
                            onChange={(e) => setMobileLast4(e.target.value.replace(/\D/g, ''))}
                            placeholder="e.g. 3210"
                            className="kiosk-input kiosk-input-otp"
                            autoFocus
                        />
                    </div>
                    <button
                        className="btn-kiosk-primary"
                        onClick={handleInitiate}
                        disabled={aadhaarLast4.length !== 4 || mobileLast4.length !== 4 || loading}
                    >
                        {loading ? '⏳ Sending OTP...' : '📲 Send OTP'}
                    </button>
                </div>
            )}

            {phase === 'otp' && (
                <div className="kiosk-form">
                    <div className="kiosk-otp-sent">
                        📱 OTP sent to mobile ending in ****{mobileLast4}
                    </div>

                    {/* OTP on-screen display (demo accommodation) */}
                    {otpDisplay && (
                        <div style={{
                            background: 'linear-gradient(135deg, #fef3c7, #fde68a)',
                            border: '2px solid #f59e0b',
                            borderRadius: '12px',
                            padding: '1.25rem',
                            textAlign: 'center',
                            marginBottom: '1rem',
                        }}>
                            <div style={{ fontWeight: '600', color: '#92400e', marginBottom: '0.5rem', fontSize: '0.85rem' }}>
                                📋 OTP for Verification (Demo Only)
                            </div>
                            <div style={{
                                fontSize: '2.5rem',
                                fontWeight: '800',
                                letterSpacing: '0.5em',
                                fontFamily: 'monospace',
                                color: '#78350f',
                            }}>
                                {otpDisplay}
                            </div>
                            <div style={{ color: '#92400e', fontSize: '0.75rem', marginTop: '0.5rem' }}>
                                ⚠️ Production: OTP is delivered via SMS only
                            </div>
                        </div>
                    )}

                    <div className="kiosk-form-group">
                        <label>Enter OTP</label>
                        <input
                            type="text"
                            maxLength={6}
                            pattern="[0-9]*"
                            inputMode="numeric"
                            value={otp}
                            onChange={(e) => setOtp(e.target.value.replace(/\D/g, ''))}
                            placeholder="Enter 6-digit OTP"
                            className="kiosk-input kiosk-input-otp"
                            autoFocus
                        />
                    </div>
                    <div className="kiosk-btn-row">
                        <button
                            className="btn-kiosk-secondary"
                            onClick={() => { setPhase('input'); setOtp(''); setOtpDisplay(''); }}
                        >
                            ← Back
                        </button>
                        <button
                            className="btn-kiosk-primary"
                            onClick={handleVerify}
                            disabled={otp.length < 4 || loading}
                        >
                            {loading ? '⏳ Verifying...' : '✓ Verify OTP'}
                        </button>
                    </div>
                </div>
            )}
        </div>
    );
}
