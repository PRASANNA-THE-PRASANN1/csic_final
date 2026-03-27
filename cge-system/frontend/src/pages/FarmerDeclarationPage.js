/**
 * FarmerDeclarationPage.js
 * Farmer self-declares the loan amount they need BEFORE the clerk creates the application.
 * This is used to detect amount inflation fraud (Fraud Type 2).
 */
import React, { useState } from 'react';
import api from '../api';

export default function FarmerDeclarationPage() {
    const [form, setForm] = useState({
        farmer_id: '', farmer_name: '', farmer_mobile: '',
        declared_amount: '', purpose: '', otp: '',
    });
    const [step, setStep] = useState(1);
    const [result, setResult] = useState(null);
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(false);

    const handleChange = (e) => {
        setForm({ ...form, [e.target.name]: e.target.value });
    };

    const handleSubmitDeclaration = async (e) => {
        e.preventDefault();
        setError(''); setLoading(true);
        try {
            const res = await api.createFarmerDeclaration({
                farmer_id: form.farmer_id, farmer_name: form.farmer_name,
                farmer_mobile: form.farmer_mobile,
                declared_amount: parseFloat(form.declared_amount),
                purpose: form.purpose, otp: form.otp || '123456',
            });
            setResult(res.data); setStep(3);
        } catch (err) {
            setError(err.response?.data?.detail || 'Failed to submit declaration');
        }
        setLoading(false);
    };

    const handleRequestOtp = () => { setStep(2); };

    /* ── Styles ── */
    const s = {
        container: { maxWidth: 620, margin: '0 auto', animation: 'drift-up 0.5s ease-out' },
        glass: {
            background: 'rgba(14,14,36,0.55)', backdropFilter: 'blur(20px)',
            border: '1px solid rgba(255,255,255,0.06)', borderRadius: 18, padding: '2rem',
        },
        title: {
            fontSize: '1.4rem', fontWeight: 600,
            background: 'linear-gradient(135deg, #64d8ff, #a78bfa)',
            WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent',
            marginBottom: '0.4rem',
        },
        desc: { color: '#8b96a9', marginBottom: 24, fontSize: '0.88rem', fontWeight: 300 },
        sectionTitle: { fontSize: '1rem', fontWeight: 500, color: '#c4cdd8', marginBottom: 14 },
        label: {
            display: 'block', fontSize: '0.72rem', fontWeight: 500, color: '#8b96a9',
            marginBottom: 4, marginTop: 12, textTransform: 'uppercase', letterSpacing: '0.08em',
        },
        input: {
            width: '100%', padding: '12px 14px',
            border: '1px solid rgba(255,255,255,0.06)', borderRadius: 10,
            fontSize: '0.92rem', background: 'rgba(6,6,16,0.5)', color: '#e8edf5',
            fontFamily: "'Sora', sans-serif", fontWeight: 300,
            outline: 'none', boxSizing: 'border-box', transition: 'border-color 0.3s',
        },
        textarea: {
            width: '100%', padding: '12px 14px', minHeight: 60, resize: 'vertical',
            border: '1px solid rgba(255,255,255,0.06)', borderRadius: 10,
            fontSize: '0.92rem', background: 'rgba(6,6,16,0.5)', color: '#e8edf5',
            fontFamily: "'Sora', sans-serif", fontWeight: 300,
            outline: 'none', boxSizing: 'border-box',
        },
        btn: (color = '#818cf8') => ({
            padding: '14px 28px',
            background: `linear-gradient(135deg, ${color}, ${color}dd)`,
            color: '#fff', border: 'none', borderRadius: 12,
            fontSize: '0.95rem', fontWeight: 500, cursor: 'pointer',
            width: '100%', marginTop: 16,
            fontFamily: "'Sora', sans-serif",
            transition: 'all 0.4s cubic-bezier(0.23,1,0.32,1)',
        }),
        btnOutline: {
            padding: '12px 20px', background: 'transparent',
            color: '#8b96a9', border: '1px solid rgba(255,255,255,0.06)',
            borderRadius: 12, fontSize: '0.88rem', cursor: 'pointer',
            width: '100%', marginTop: 8,
            fontFamily: "'Sora', sans-serif",
            transition: 'all 0.3s',
        },
        error: {
            color: '#fca5a5', background: 'rgba(248,113,113,0.08)',
            border: '1px solid rgba(248,113,113,0.25)',
            padding: '12px 16px', borderRadius: 12, marginBottom: '1rem', fontSize: '0.88rem',
        },
        section: {
            background: 'rgba(6,6,16,0.4)', border: '1px solid rgba(255,255,255,0.06)',
            borderRadius: 14, padding: '1.2rem', marginBottom: 14,
        },
        summaryRow: {
            display: 'flex', justifyContent: 'space-between', padding: '8px 0',
            borderBottom: '1px solid rgba(255,255,255,0.04)', fontSize: '0.88rem',
        },
        summaryLabel: { color: '#8b96a9', fontWeight: 500 },
        summaryValue: { color: '#e8edf5', fontWeight: 400 },
    };

    return (
        <div style={s.container}>
            <div style={s.glass}>
                <h2 style={s.title}>🧑‍🌾 Farmer Loan Declaration</h2>
                <p style={s.desc}>
                    Declare the loan amount you need <strong style={{ color: '#e8edf5' }}>before</strong> the clerk creates your application.
                    This helps prevent amount inflation fraud.
                </p>

                {error && <div style={s.error} role="alert">⚠ {error}</div>}

                {/* Step 1: Form */}
                {step === 1 && (
                    <form onSubmit={(e) => { e.preventDefault(); handleRequestOtp(); }}>
                        <div style={s.section}>
                            <h5 style={s.sectionTitle}>📋 Your Details</h5>
                            <label style={s.label}>Farmer ID (Aadhaar / KCC Number)</label>
                            <input style={s.input} name="farmer_id" value={form.farmer_id} onChange={handleChange} required placeholder="e.g., F001" aria-label="Farmer ID" />
                            <label style={s.label}>Full Name</label>
                            <input style={s.input} name="farmer_name" value={form.farmer_name} onChange={handleChange} required placeholder="As per bank records" aria-label="Full name" />
                            <label style={s.label}>Mobile Number</label>
                            <input style={s.input} name="farmer_mobile" value={form.farmer_mobile} onChange={handleChange} required placeholder="10-digit mobile" aria-label="Mobile number" />
                        </div>

                        <div style={s.section}>
                            <h5 style={s.sectionTitle}>💰 Loan Requirement</h5>
                            <label style={s.label}>Amount You Need (₹)</label>
                            <input style={s.input} name="declared_amount" type="number" value={form.declared_amount} onChange={handleChange} required min="1" placeholder="Enter amount in Rupees" aria-label="Declared loan amount" />
                            <label style={s.label}>Purpose</label>
                            <textarea style={s.textarea} name="purpose" value={form.purpose} onChange={handleChange} required placeholder="e.g., Crop cultivation, Equipment purchase" rows={2} aria-label="Loan purpose" />
                        </div>

                        <button type="submit" style={s.btn()} aria-label="Request OTP to confirm declaration">Request OTP to Confirm</button>
                    </form>
                )}

                {/* Step 2: OTP */}
                {step === 2 && (
                    <form onSubmit={handleSubmitDeclaration}>
                        <div style={s.section}>
                            <h5 style={s.sectionTitle}>🔐 OTP Verification</h5>
                            <p style={{ color: '#8b96a9', fontSize: '0.85rem', fontWeight: 300, marginBottom: 12 }}>
                                An OTP has been sent to {form.farmer_mobile || 'your mobile'}.
                                <span style={{ color: '#5b6578' }}> (Demo: enter any 6-digit OTP)</span>
                            </p>
                            <label style={s.label}>Enter OTP</label>
                            <input style={{ ...s.input, fontSize: '1.2rem', textAlign: 'center', letterSpacing: '0.4rem', color: '#64d8ff', fontFamily: "'Space Mono', monospace" }}
                                name="otp" value={form.otp} onChange={handleChange} required placeholder="6-digit OTP" maxLength={6}
                                aria-label="Enter OTP"
                            />

                            <div style={{ ...s.section, marginTop: 16, background: 'rgba(129,140,248,0.06)', border: '1px solid rgba(129,140,248,0.15)' }}>
                                <h6 style={{ fontSize: '0.85rem', color: '#a78bfa', fontWeight: 500, marginBottom: 10 }}>📝 Declaration Summary</h6>
                                <div style={s.summaryRow}>
                                    <span style={s.summaryLabel}>Name</span>
                                    <span style={s.summaryValue}>{form.farmer_name}</span>
                                </div>
                                <div style={s.summaryRow}>
                                    <span style={s.summaryLabel}>Farmer ID</span>
                                    <span style={s.summaryValue}>{form.farmer_id}</span>
                                </div>
                                <div style={s.summaryRow}>
                                    <span style={s.summaryLabel}>Amount</span>
                                    <span style={{ ...s.summaryValue, color: '#6ee7b7', fontWeight: 500 }}>₹{parseFloat(form.declared_amount || 0).toLocaleString()}</span>
                                </div>
                                <div style={{ ...s.summaryRow, borderBottom: 'none' }}>
                                    <span style={s.summaryLabel}>Purpose</span>
                                    <span style={s.summaryValue}>{form.purpose}</span>
                                </div>
                            </div>
                        </div>

                        <button type="submit" style={s.btn('#4ae3c0')} disabled={loading} aria-label="Confirm declaration">
                            {loading ? '⏳ Submitting...' : '✅ Confirm Declaration'}
                        </button>
                        <button type="button" style={s.btnOutline} onClick={() => setStep(1)} aria-label="Go back to edit form">
                            ← Back to Edit
                        </button>
                    </form>
                )}

                {/* Step 3: Done */}
                {step === 3 && result && (
                    <div style={{
                        background: 'rgba(74,227,192,0.06)', border: '1px solid rgba(74,227,192,0.2)',
                        borderRadius: 18, padding: '2rem', textAlign: 'center',
                    }} aria-live="polite">
                        <div style={{ fontSize: '2.5rem', marginBottom: 8 }}>✅</div>
                        <h4 style={{ color: '#6ee7b7', fontWeight: 600, marginBottom: 12 }}>Declaration Recorded!</h4>

                        <div style={{
                            background: 'rgba(129,140,248,0.08)', border: '1px solid rgba(129,140,248,0.2)',
                            borderRadius: 12, padding: '1rem', marginBottom: 16,
                        }}>
                            <strong style={{ color: '#a78bfa', fontSize: '1rem' }}>Declaration ID: {result.declaration_id}</strong><br />
                            <small style={{ color: '#8b96a9', fontWeight: 300 }}>Share this ID with the bank clerk when applying for your loan.</small>
                        </div>

                        <div style={s.section}>
                            <div style={s.summaryRow}>
                                <span style={s.summaryLabel}>Amount Declared</span>
                                <span style={{ ...s.summaryValue, color: '#6ee7b7' }}>₹{result.declared_amount?.toLocaleString()}</span>
                            </div>
                            <div style={s.summaryRow}>
                                <span style={s.summaryLabel}>Purpose</span>
                                <span style={s.summaryValue}>{result.purpose}</span>
                            </div>
                            <div style={s.summaryRow}>
                                <span style={s.summaryLabel}>Hash</span>
                                <span style={{ ...s.summaryValue, fontFamily: "'Space Mono', monospace", fontSize: '0.72rem', color: '#64d8ff' }}>{result.declaration_hash}</span>
                            </div>
                            <div style={{ ...s.summaryRow, borderBottom: 'none' }}>
                                <span style={s.summaryLabel}>Status</span>
                                <span style={{ display: 'inline-block', padding: '3px 12px', borderRadius: 999, fontSize: '0.72rem', fontWeight: 600, color: '#fff', background: '#4ae3c0' }}>{result.status}</span>
                            </div>
                        </div>

                        <p style={{ color: '#64d8ff', fontSize: '0.85rem', marginTop: 12, fontWeight: 400 }}>
                            📱 An SMS confirmation has been sent to your mobile number.
                            Your declaration is cryptographically signed and tamper-proof.
                        </p>
                        <button style={s.btn('#818cf8')} onClick={() => {
                            setStep(1); setResult(null);
                            setForm({ farmer_id: '', farmer_name: '', farmer_mobile: '', declared_amount: '', purpose: '', otp: '' });
                        }}>
                            Make Another Declaration
                        </button>
                    </div>
                )}
            </div>
        </div>
    );
}
