/**
 * KioskConsentConfirm — Final consent step: IVR voice confirmation only.
 * No OTP required. Shows loan summary, then directly triggers IVR call
 * with 60-second countdown for farmer to confirm via phone (press 1).
 */

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useKiosk } from './KioskContext';
import { kioskConsentInitiate, kioskComplete, kioskIvrStatus } from '../api';

function amountInWords(amount) {
    if (!amount || isNaN(amount)) return '';
    const num = Number(amount);
    if (num >= 10000000) return `₹${(num / 10000000).toFixed(2)} Crore`;
    if (num >= 100000) return `₹${(num / 100000).toFixed(2)} Lakh`;
    if (num >= 1000) return `₹${(num / 1000).toFixed(1)} Thousand`;
    return `₹${num.toLocaleString('en-IN')}`;
}

function amountInHindi(amount) {
    if (!amount || isNaN(amount)) return '';
    const num = Number(amount);
    if (num >= 10000000) return `₹${(num / 10000000).toFixed(2)} करोड़`;
    if (num >= 100000) return `₹${(num / 100000).toFixed(2)} लाख`;
    if (num >= 1000) return `₹${(num / 1000).toFixed(1)} हज़ार`;
    return `₹${num.toLocaleString('en-IN')}`;
}

export default function KioskConsentConfirm() {
    const { state, dispatch } = useKiosk();
    // Phases: 'summary' | 'ivr' | 'confirmed' | 'rejected' | 'timed_out'
    const [phase, setPhase] = useState('summary');
    const [loading, setLoading] = useState(false);

    const [ivrCountdown, setIvrCountdown] = useState(300);
    const [ivrMethod, setIvrMethod] = useState('call'); // 'call' or 'sms'
    const ivrTimerRef = useRef(null);
    const pollRef = useRef(null);
    const completingRef = useRef(false);

    // Local countdown timer (visual only — server poll is source of truth for timeout)
    useEffect(() => {
        if (phase === 'ivr') {
            ivrTimerRef.current = setInterval(() => {
                setIvrCountdown(prev => {
                    if (prev <= 1) {
                        clearInterval(ivrTimerRef.current);
                        // Do NOT set timed_out here — let the server poll decide
                        return 0;
                    }
                    return prev - 1;
                });
            }, 1000);
            return () => clearInterval(ivrTimerRef.current);
        }
    }, [phase]);

    // Poll IVR status every 2 seconds
    const stopPolling = useCallback(() => {
        if (pollRef.current) {
            clearInterval(pollRef.current);
            pollRef.current = null;
        }
        if (ivrTimerRef.current) {
            clearInterval(ivrTimerRef.current);
            ivrTimerRef.current = null;
        }
    }, []);

    useEffect(() => {
        if (phase === 'ivr') {
            let firstPoll = true;
            const poll = async () => {
                try {
                    const res = await kioskIvrStatus(state.loanId, state.sessionToken);
                    const data = res.data;

                    if (data.remaining_seconds !== undefined) {
                        const serverRemaining = Math.ceil(data.remaining_seconds);
                        if (firstPoll) {
                            setIvrCountdown(serverRemaining);
                            firstPoll = false;
                        } else {
                            setIvrCountdown(prev => {
                                const drift = Math.abs(prev - serverRemaining);
                                return drift > 3 ? serverRemaining : prev;
                            });
                        }
                    }

                    if (data.consent_final_method === 'sms') {
                        setIvrMethod('sms');
                    }

                    if (data.ivr_status === 'confirmed') {
                        stopPolling();
                        setPhase('confirmed');
                    } else if (data.ivr_status === 'rejected') {
                        stopPolling();
                        setPhase('rejected');
                    } else if (data.ivr_status === 'timed_out') {
                        stopPolling();
                        setPhase('timed_out');
                    }
                } catch (err) {
                    console.error('IVR poll error:', err);
                }
            };

            poll();
            pollRef.current = setInterval(poll, 2000);
            return () => stopPolling();
        }
    }, [phase, state.loanId, state.sessionToken, stopPolling]);

    // Auto-complete on confirmed
    useEffect(() => {
        if (phase === 'confirmed' && !completingRef.current) {
            completingRef.current = true;
            const completeKiosk = async () => {
                setLoading(true);
                try {
                    const complete = await kioskComplete(state.loanId, state.sessionToken);
                    dispatch({ type: 'SET_CONSENT_COMPLETE' });
                    dispatch({
                        type: 'SET_ANCHOR',
                        hash: complete.data.kiosk_phase_anchor_hash,
                        blockNumber: complete.data.block_number,
                    });
                    dispatch({ type: 'NEXT_STEP' });
                } catch (err) {
                    console.log('Auto-complete may have been done by webhook:', err);
                    dispatch({ type: 'SET_CONSENT_COMPLETE' });
                    dispatch({ type: 'NEXT_STEP' });
                } finally {
                    setLoading(false);
                }
            };
            const timeout = setTimeout(completeKiosk, 1500);
            return () => clearTimeout(timeout);
        }
    }, [phase, state.loanId, state.sessionToken, dispatch]);

    // Directly trigger IVR call (skip OTP)
    const handleInitiateIVR = async () => {
        setLoading(true);
        dispatch({ type: 'SET_ERROR', error: null });
        try {
            // Call consent/initiate-ivr which triggers IVR directly (no OTP)
            const res = await fetch(
                `${process.env.REACT_APP_API_URL || 'http://localhost:8000'}/api/kiosk/${state.loanId}/consent/initiate-ivr`,
                {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-Session-Token': state.sessionToken,
                    },
                    body: JSON.stringify({}),
                }
            );
            const data = await res.json();
            if (!res.ok) {
                throw new Error(data.detail || 'Failed to initiate IVR call');
            }

            dispatch({ type: 'SET_CONSENT_COMPLETE' });

            if (data.ivr_initiated) {
                setIvrCountdown(300);
                setIvrMethod('call');
                setPhase('ivr');
            } else {
                throw new Error(data.ivr_error || 'IVR call could not be initiated');
            }
        } catch (err) {
            dispatch({ type: 'SET_ERROR', error: err.message || 'Failed to initiate consent call' });
        } finally {
            setLoading(false);
        }
    };

    // Estimated EMI
    const amount = Number(state.amount || 0);
    const monthlyRate = 0.09 / 12;
    const tenure = amount < 200000 ? 12 : (amount < 1000000 ? 24 : 36);
    const emi = amount > 0
        ? Math.round(amount * monthlyRate * Math.pow(1 + monthlyRate, tenure) / (Math.pow(1 + monthlyRate, tenure) - 1))
        : 0;

    // IVR countdown circle
    const ivrCircleDash = (ivrCountdown / 300) * 339.3;

    return (
        <div className="kiosk-step kiosk-consent">
            <h2 className="kiosk-step-title">🔏 Final Consent / अंतिम सहमति</h2>

            {/* ──── PHASE: Summary → Direct IVR ──── */}
            {phase === 'summary' && (
                <div className="kiosk-consent-summary">
                    <p className="kiosk-step-subtitle">
                        Please review the loan details below. A voice call will be placed
                        to the registered number for final confirmation.
                        <br />
                        <span className="kiosk-hindi">कृपया ऋण विवरण की समीक्षा करें। अंतिम पुष्टि के लिए पंजीकृत नंबर पर कॉल आएगी।</span>
                    </p>
                    <div className="kiosk-summary-card">
                        <div className="kiosk-summary-row">
                            <span className="label">Applicant Name / आवेदक</span>
                            <span className="value">{state.farmerName}</span>
                        </div>
                        <div className="kiosk-summary-row">
                            <span className="label">Loan Amount / ऋण राशि</span>
                            <span className="value highlight">
                                ₹{amount.toLocaleString('en-IN')}
                                <span className="kiosk-amount-words">
                                    ({amountInWords(amount)} / {amountInHindi(amount)})
                                </span>
                            </span>
                        </div>
                        <div className="kiosk-summary-row">
                            <span className="label">Purpose / उद्देश्य</span>
                            <span className="value">{state.purpose}</span>
                        </div>
                        <div className="kiosk-summary-row">
                            <span className="label">Est. EMI / अनुमानित EMI</span>
                            <span className="value">≈ ₹{emi.toLocaleString('en-IN')}/month ({tenure} months)</span>
                        </div>
                        <div className="kiosk-summary-row">
                            <span className="label">Loan ID / ऋण आईडी</span>
                            <span className="value mono">{state.loanId}</span>
                        </div>
                    </div>

                    {state.assistanceRequested && (
                        <div className="kiosk-assistance-note">
                            👤 Assisted by a bank employee — details are recorded on the system.
                        </div>
                    )}

                    <div className="kiosk-consent-warning">
                        ⚠️ By proceeding, a voice call will be placed to confirm this loan.
                        Press <strong>1</strong> on the call to confirm, <strong>2</strong> to reject.
                        <br />
                        <span className="kiosk-hindi">
                            आगे बढ़ने पर एक कॉल आएगी। पुष्टि के लिए 1 दबाएँ, अस्वीकार के लिए 2 दबाएँ।
                        </span>
                    </div>

                    <button
                        className="btn-kiosk-primary"
                        onClick={handleInitiateIVR}
                        disabled={loading}
                    >
                        {loading ? '⏳ Placing Confirmation Call...' : '📞 I Agree — Place Confirmation Call'}
                    </button>
                </div>
            )}

            {/* ──── PHASE: IVR Waiting (60-second window) ──── */}
            {phase === 'ivr' && (
                <div className="kiosk-ivr-phase">
                    <div className="kiosk-ivr-header">
                        <h3 style={{ margin: '0 0 8px', fontSize: '1.3rem', color: '#fff' }}>
                            📞 Voice Confirmation Required
                        </h3>
                        <p style={{ margin: 0, opacity: 0.85, fontSize: '0.95rem' }}>
                            अंतिम पुष्टि के लिए कॉल का जवाब दें
                        </p>
                    </div>

                    {/* 60-second countdown circle */}
                    <div className="kiosk-countdown-container">
                        <div className="kiosk-countdown-circle">
                            <svg width="140" height="140" viewBox="0 0 140 140">
                                <circle cx="70" cy="70" r="62" fill="none" stroke="rgba(255,255,255,0.15)" strokeWidth="8" />
                                <circle
                                    cx="70" cy="70" r="62"
                                    fill="none"
                                    stroke={ivrCountdown > 15 ? '#4caf50' : ivrCountdown > 5 ? '#ff9800' : '#f44336'}
                                    strokeWidth="8"
                                    strokeDasharray={`${ivrCircleDash} 389.6`}
                                    strokeLinecap="round"
                                    transform="rotate(-90 70 70)"
                                    style={{ transition: 'stroke-dasharray 1s linear, stroke 0.5s' }}
                                />
                            </svg>
                            <span className="kiosk-countdown-number" style={{ fontSize: '2.2rem', fontWeight: 700 }}>
                                {ivrCountdown}
                            </span>
                        </div>
                    </div>

                    {/* Status message */}
                    <div className="kiosk-ivr-status-msg" style={{
                        background: 'rgba(255,255,255,0.1)',
                        borderRadius: '12px',
                        padding: '20px',
                        margin: '16px 0',
                        textAlign: 'center',
                        fontSize: '1.1rem',
                        lineHeight: 1.6,
                    }}>
                        {ivrMethod === 'call' ? (
                            <>
                                <div style={{ fontSize: '2rem', marginBottom: '8px' }}>📞</div>
                                <div>Call placed to your registered number.</div>
                                <div style={{ fontWeight: 600, marginTop: '4px' }}>
                                    Press <span style={{ color: '#4caf50', fontSize: '1.3rem' }}>1</span> to confirm,
                                    Press <span style={{ color: '#f44336', fontSize: '1.3rem' }}>2</span> to reject.
                                </div>
                                <div className="kiosk-hindi" style={{ marginTop: '8px', opacity: 0.85 }}>
                                    कॉल आ रही है। पुष्टि के लिए 1 दबाएँ, अस्वीकार के लिए 2 दबाएँ।
                                </div>
                            </>
                        ) : (
                            <>
                                <div style={{ fontSize: '2rem', marginBottom: '8px' }}>📱</div>
                                <div>SMS sent to your registered number.</div>
                                <div style={{ fontWeight: 600, marginTop: '4px' }}>
                                    Reply <span style={{ color: '#4caf50' }}>YES</span> to confirm
                                    or <span style={{ color: '#f44336' }}>NO</span> to reject.
                                </div>
                                <div className="kiosk-hindi" style={{ marginTop: '8px', opacity: 0.85 }}>
                                    SMS भेजा गया। पुष्टि के लिए YES लिखें, अस्वीकार के लिए NO लिखें।
                                </div>
                            </>
                        )}
                    </div>

                    <div className="kiosk-spinner"></div>
                    <p style={{ textAlign: 'center', opacity: 0.7, fontSize: '0.9rem' }}>
                        Waiting for response... / प्रतिक्रिया की प्रतीक्षा...
                    </p>
                </div>
            )}

            {/* ──── PHASE: Confirmed ✅ ──── */}
            {phase === 'confirmed' && (
                <div className="kiosk-ivr-result" style={{
                    background: 'linear-gradient(135deg, #1b5e20, #2e7d32)',
                    borderRadius: '16px',
                    padding: '48px 32px',
                    textAlign: 'center',
                    color: '#fff',
                }}>
                    <div style={{ fontSize: '4rem', marginBottom: '16px' }}>✅</div>
                    <h3 style={{ fontSize: '1.6rem', margin: '0 0 8px' }}>Consent Confirmed</h3>
                    <p style={{ fontSize: '1.1rem', opacity: 0.9 }}>सहमति की पुष्टि हो गई</p>
                    <p style={{ marginTop: '16px', opacity: 0.8 }}>Completing your application...</p>
                    {loading && <div className="kiosk-spinner" style={{ marginTop: '16px' }}></div>}
                </div>
            )}

            {/* ──── PHASE: Rejected ❌ ──── */}
            {phase === 'rejected' && (
                <div className="kiosk-ivr-result" style={{
                    background: 'linear-gradient(135deg, #b71c1c, #c62828)',
                    borderRadius: '16px',
                    padding: '48px 32px',
                    textAlign: 'center',
                    color: '#fff',
                }}>
                    <div style={{ fontSize: '4rem', marginBottom: '16px' }}>❌</div>
                    <h3 style={{ fontSize: '1.6rem', margin: '0 0 8px' }}>Loan Application Rejected</h3>
                    <p style={{ fontSize: '1.1rem', opacity: 0.9 }}>आपने इस ऋण आवेदन को अस्वीकार कर दिया है।</p>
                    <p style={{ marginTop: '16px', opacity: 0.8, fontSize: '0.95rem' }}>
                        This session has ended. Please visit the bank to start a new application.
                    </p>
                </div>
            )}

            {/* ──── PHASE: Timed Out ⏱ ──── */}
            {phase === 'timed_out' && (
                <div className="kiosk-ivr-result" style={{
                    background: 'linear-gradient(135deg, #e65100, #ef6c00)',
                    borderRadius: '16px',
                    padding: '48px 32px',
                    textAlign: 'center',
                    color: '#fff',
                }}>
                    <div style={{ fontSize: '4rem', marginBottom: '16px' }}>⏱</div>
                    <h3 style={{ fontSize: '1.6rem', margin: '0 0 8px' }}>Time Expired</h3>
                    <p style={{ fontSize: '1.1rem', opacity: 0.9 }}>समय समाप्त हो गया</p>
                    <p style={{ marginTop: '16px', opacity: 0.8, fontSize: '0.95rem' }}>
                        This application has been rejected. Please visit the bank to start a new application.
                    </p>
                </div>
            )}
        </div>
    );
}
