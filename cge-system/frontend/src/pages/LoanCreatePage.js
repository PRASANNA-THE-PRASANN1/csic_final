/**
 * LoanCreatePage.js – Clerk creates loan with farmer declaration linkage.
 * Shows SMS notification preview after successful creation.
 */

import React, { useState, useEffect, useCallback } from 'react';
import { createLoan, getTierInfo, getFarmerDeclaration } from '../api';

export default function LoanCreatePage() {
    const [form, setForm] = useState({
        farmer_id: '', farmer_name: '', farmer_mobile: '', amount: '',
        tenure_months: 12, interest_rate: 7.0, purpose: '', created_by: '',
        declaration_id: '', amount_difference_reason: '',
    });
    const [tierInfo, setTierInfo] = useState(null);
    const [declaration, setDeclaration] = useState(null);
    const [declLoading, setDeclLoading] = useState(false);
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(false);
    const [result, setResult] = useState(null);

    useEffect(() => {
        const amt = parseFloat(form.amount);
        if (amt > 0) {
            getTierInfo(amt).then((r) => setTierInfo(r.data)).catch(() => setTierInfo(null));
        } else { setTierInfo(null); }
    }, [form.amount]);

    const lookupDeclaration = useCallback(async () => {
        if (!form.declaration_id.trim()) return;
        setDeclLoading(true);
        try {
            const res = await getFarmerDeclaration(form.declaration_id.trim());
            setDeclaration(res.data);
            setForm((prev) => ({
                ...prev,
                farmer_id: res.data.farmer_id || prev.farmer_id,
                farmer_name: res.data.farmer_name || prev.farmer_name,
                farmer_mobile: res.data.farmer_mobile || prev.farmer_mobile,
                purpose: res.data.purpose || prev.purpose,
            }));
        } catch (e) { setDeclaration(null); setError('Declaration not found'); }
        setDeclLoading(false);
    }, [form.declaration_id]);

    const handleChange = (e) => {
        setForm({ ...form, [e.target.name]: e.target.value });
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        setError('');
        setLoading(true);
        try {
            const res = await createLoan({
                ...form,
                amount: parseFloat(form.amount),
                tenure_months: parseInt(form.tenure_months, 10),
                interest_rate: parseFloat(form.interest_rate),
                declaration_id: form.declaration_id || null,
                amount_difference_reason: form.amount_difference_reason || null,
            });
            setResult(res.data);
        } catch (e) {
            const detail = e.response?.data?.detail;
            if (typeof detail === 'object') { setError(JSON.stringify(detail)); }
            else { setError(detail || 'Failed to create loan'); }
        }
        setLoading(false);
    };

    /* ── Styles ── */
    const s = {
        container: { maxWidth: 720, margin: '0 auto', animation: 'drift-up 0.5s ease-out' },
        glass: {
            background: 'rgba(14,14,36,0.55)', backdropFilter: 'blur(20px)',
            border: '1px solid rgba(255,255,255,0.06)', borderRadius: 18, padding: '2rem',
        },
        title: {
            fontSize: '1.5rem', fontWeight: 600,
            background: 'linear-gradient(135deg, #64d8ff, #a78bfa)',
            WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent',
            marginBottom: '1.5rem', letterSpacing: '0.02em',
        },
        label: {
            display: 'block', fontSize: '0.72rem', fontWeight: 500,
            color: '#8b96a9', marginBottom: 4, marginTop: 14,
            textTransform: 'uppercase', letterSpacing: '0.08em',
        },
        input: {
            width: '100%', padding: '12px 14px',
            border: '1px solid rgba(255,255,255,0.06)', borderRadius: 10,
            fontSize: '0.92rem', background: 'rgba(6,6,16,0.5)', color: '#e8edf5',
            fontFamily: "'Sora', sans-serif", fontWeight: 300,
            outline: 'none', boxSizing: 'border-box', transition: 'border-color 0.3s',
        },
        row: { display: 'flex', gap: 16 },
        btn: (color = '#818cf8') => ({
            padding: '14px 28px',
            background: `linear-gradient(135deg, ${color}, ${color}dd)`,
            color: '#fff', border: 'none', borderRadius: 12,
            fontSize: '1rem', fontWeight: 500, cursor: 'pointer',
            width: '100%', marginTop: 20,
            fontFamily: "'Sora', sans-serif",
            transition: 'all 0.4s cubic-bezier(0.23,1,0.32,1)',
            letterSpacing: '0.02em',
        }),
        tierBox: {
            background: 'rgba(129,140,248,0.08)', border: '1px solid rgba(129,140,248,0.2)',
            borderRadius: 12, padding: '12px 16px', marginTop: 12,
            display: 'flex', justifyContent: 'space-between', alignItems: 'center',
            color: '#c4cdd8', fontSize: '0.88rem',
        },
        declBox: {
            background: 'rgba(251,191,36,0.06)', border: '1px solid rgba(251,191,36,0.2)',
            borderRadius: 12, padding: '14px 16px', marginTop: 12,
            fontSize: '0.9rem', color: '#c4cdd8', fontWeight: 300,
        },
        amountDiff: {
            background: 'rgba(248,113,113,0.08)', border: '1px solid rgba(248,113,113,0.25)',
            borderRadius: 10, padding: '12px 16px', marginTop: 8,
            fontWeight: 500, color: '#fca5a5',
        },
        notifPreview: {
            background: 'rgba(74,227,192,0.06)', border: '1px solid rgba(74,227,192,0.2)',
            borderRadius: 16, padding: '1.5rem', marginTop: 20,
        },
        smsBox: {
            background: 'rgba(6,6,16,0.5)', borderRadius: 10, padding: '1rem',
            fontFamily: "'Space Mono', monospace", fontSize: '0.82rem', lineHeight: 1.8,
            border: '1px solid rgba(74,227,192,0.15)', marginTop: 12, color: '#64d8ff',
        },
        error: {
            color: '#fca5a5', background: 'rgba(248,113,113,0.08)',
            border: '1px solid rgba(248,113,113,0.25)',
            padding: '12px 16px', borderRadius: 12, marginBottom: '1rem',
            fontSize: '0.88rem',
        },
    };

    /* ── Success View ── */
    if (result) {
        const amt = parseFloat(result.amount) || 0;
        return (
            <div style={s.container}>
                <div style={s.glass} aria-live="polite">
                    <h1 style={{ ...s.title, background: 'linear-gradient(135deg, #4ae3c0, #6ee7b7)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
                        ✅ Loan Created Successfully
                    </h1>

                    <div style={{ lineHeight: 2, fontSize: '0.9rem', color: '#c4cdd8', fontWeight: 300 }}>
                        <strong style={{ color: '#e8edf5', fontWeight: 500 }}>Loan ID:</strong>{' '}
                        <code style={{ fontSize: '0.78rem', color: '#64d8ff', background: 'rgba(100,216,255,0.06)', padding: '2px 6px', borderRadius: 4, fontFamily: "'Space Mono', monospace" }}>
                            {result.loan_id}
                        </code><br />
                        <strong style={{ color: '#e8edf5', fontWeight: 500 }}>Farmer:</strong> {result.farmer_name} ({result.farmer_id})<br />
                        <strong style={{ color: '#e8edf5', fontWeight: 500 }}>Amount:</strong> ₹{amt.toLocaleString('en-IN')}<br />
                        <strong style={{ color: '#e8edf5', fontWeight: 500 }}>Purpose:</strong> {result.purpose}<br />
                        <strong style={{ color: '#e8edf5', fontWeight: 500 }}>Status:</strong> {result.status}<br />
                        <strong style={{ color: '#e8edf5', fontWeight: 500 }}>Tier:</strong> {result.approval_tier}<br />
                        <strong style={{ color: '#e8edf5', fontWeight: 500 }}>Loan Hash:</strong>{' '}
                        <code style={{ fontSize: '0.75rem', color: '#64d8ff', background: 'rgba(100,216,255,0.06)', padding: '2px 6px', borderRadius: 4, fontFamily: "'Space Mono', monospace" }}>
                            {result.loan_hash?.slice(0, 32)}...
                        </code>
                    </div>

                    {/* SMS Notification Preview */}
                    <div style={s.notifPreview}>
                        <h3 style={{ margin: 0, color: '#4ae3c0', fontWeight: 500, fontSize: '1rem' }}>📱 SMS Notification Sent to Farmer</h3>
                        <p style={{ color: '#8b96a9', margin: '4px 0 0', fontWeight: 300, fontSize: '0.85rem' }}>
                            Mobile: +91-{result.farmer_mobile}
                        </p>
                        <div style={s.smsBox}>
                            Loan application created:<br />
                            Amount: Rs {amt.toLocaleString('en-IN')}<br />
                            Purpose: {result.purpose}<br />
                            Branch: DCCB Branch<br />
                            Date: {new Date().toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })}<br />
                            NOT YOU? Call: 1800-XXX-XXXX<br />
                            Loan ID: {result.loan_id}
                        </div>
                        <p style={{ fontSize: '0.82rem', color: '#4ae3c0', marginTop: 10, marginBottom: 0, fontWeight: 400 }}>
                            ✅ Delivery Status: Delivered · This SMS creates external accountability
                        </p>
                    </div>

                    {result.farmer_declared_amount && (
                        <div style={{ ...s.declBox, marginTop: 16 }}>
                            <strong style={{ color: '#fbbf24' }}>Declaration Match:</strong> Farmer declared ₹{result.farmer_declared_amount.toLocaleString('en-IN')}
                            {Math.abs(amt - result.farmer_declared_amount) > 1 && (
                                <div style={s.amountDiff}>
                                    ⚠ Difference: ₹{Math.abs(amt - result.farmer_declared_amount).toLocaleString('en-IN')}
                                    {result.amount_difference_reason && <><br />Reason: {result.amount_difference_reason}</>}
                                </div>
                            )}
                        </div>
                    )}

                    <button
                        style={s.btn('#818cf8')}
                        onClick={() => { setResult(null); setForm({ ...form, farmer_id: '', farmer_name: '', farmer_mobile: '', amount: '', purpose: '', declaration_id: '' }); }}
                    >
                        ➕ Create Another Loan
                    </button>
                </div>
            </div>
        );
    }

    /* ── Form View ── */
    return (
        <div style={s.container}>
            <div style={s.glass}>
                <h1 style={s.title}>📝 Create Loan Application</h1>

                {error && <div style={s.error} role="alert">⚠ {error}</div>}

                <form onSubmit={handleSubmit}>
                    {/* Declaration linkage */}
                    <label style={s.label}>Declaration ID (optional – Fraud Type 2 prevention)</label>
                    <div style={{ display: 'flex', gap: 8 }}>
                        <input style={{ ...s.input, flex: 1 }} name="declaration_id" placeholder="e.g. DEC1707848123000" value={form.declaration_id} onChange={handleChange} aria-label="Declaration ID" />
                        <button type="button" style={{ ...s.btn('#fbbf24'), width: 'auto', marginTop: 0, padding: '12px 20px', color: '#060610' }} onClick={lookupDeclaration} disabled={declLoading} aria-label="Look up declaration">
                            {declLoading ? '...' : '🔍'}
                        </button>
                    </div>
                    {declaration && (
                        <div style={s.declBox}>
                            <strong style={{ color: '#fbbf24' }}>📋 Declaration Found:</strong><br />
                            Farmer: {declaration.farmer_name} ({declaration.farmer_id})<br />
                            Declared Amount: ₹{declaration.declared_amount?.toLocaleString('en-IN')}<br />
                            Purpose: {declaration.purpose}
                        </div>
                    )}

                    <div style={s.row}>
                        <div style={{ flex: 1 }}>
                            <label style={s.label}>Farmer ID *</label>
                            <input style={s.input} name="farmer_id" value={form.farmer_id} onChange={handleChange} required aria-label="Farmer ID" />
                        </div>
                        <div style={{ flex: 1 }}>
                            <label style={s.label}>Farmer Name *</label>
                            <input style={s.input} name="farmer_name" value={form.farmer_name} onChange={handleChange} required aria-label="Farmer name" />
                        </div>
                    </div>

                    <label style={s.label}>Farmer Mobile *</label>
                    <input style={s.input} name="farmer_mobile" value={form.farmer_mobile} onChange={handleChange} required aria-label="Farmer mobile number" />

                    <label style={s.label}>Loan Amount (₹) *</label>
                    <input style={s.input} name="amount" type="number" value={form.amount} onChange={handleChange} required aria-label="Loan amount" />

                    {tierInfo && (
                        <div style={s.tierBox}>
                            <span>📊 <strong style={{ color: '#a78bfa' }}>Tier:</strong> {tierInfo.tier_name}</span>
                            <span style={{ fontSize: '0.82rem', color: '#8b96a9' }}>Approvals: {tierInfo.required_approvals?.map(a => a.role).join(', ')}</span>
                        </div>
                    )}

                    {declaration && form.amount && Math.abs(parseFloat(form.amount) - declaration.declared_amount) > 1 && (
                        <div>
                            <div style={s.amountDiff}>
                                ⚠ Amount differs from declaration by ₹{Math.abs(parseFloat(form.amount) - declaration.declared_amount).toLocaleString('en-IN')}
                            </div>
                            <label style={s.label}>Reason for Difference *</label>
                            <input style={s.input} name="amount_difference_reason" placeholder="e.g. Additional seeds needed" value={form.amount_difference_reason} onChange={handleChange} required aria-label="Reason for amount difference" />
                        </div>
                    )}

                    <div style={s.row}>
                        <div style={{ flex: 1 }}>
                            <label style={s.label}>Tenure (months)</label>
                            <input style={s.input} name="tenure_months" type="number" value={form.tenure_months} onChange={handleChange} aria-label="Tenure in months" />
                        </div>
                        <div style={{ flex: 1 }}>
                            <label style={s.label}>Interest Rate (%)</label>
                            <input style={s.input} name="interest_rate" type="number" step="0.1" value={form.interest_rate} onChange={handleChange} aria-label="Interest rate" />
                        </div>
                    </div>

                    <label style={s.label}>Purpose *</label>
                    <input style={s.input} name="purpose" placeholder="e.g. Crop cultivation, Tractor purchase" value={form.purpose} onChange={handleChange} required aria-label="Loan purpose" />

                    <label style={s.label}>Created By (Employee ID) *</label>
                    <input style={s.input} name="created_by" placeholder="e.g. EMP001" value={form.created_by} onChange={handleChange} required aria-label="Employee ID" />

                    <button type="submit" style={s.btn('#4ae3c0')} disabled={loading} aria-label="Create loan application">
                        {loading ? '🔄 Creating...' : '✅ Create Loan Application'}
                    </button>
                </form>
            </div>
        </div>
    );
}
