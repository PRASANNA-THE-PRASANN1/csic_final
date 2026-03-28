/**
 * KioskOCRConfirm — Displays structured OCR results and asks farmer to confirm all 9 fields.
 * Shows per-field confidence indicators, highlights low-confidence fields,
 * and supports Aadhaar masking. Sends confirmed_extras to backend.
 *
 * 3-Layer OCR integration:
 *   - If API returns manual_required: true → switches to full manual entry mode
 *   - Low-confidence fields highlighted in yellow
 *   - Shows ocr_source badge (google_vision / paddleocr / tesseract / manual)
 */

import React, { useState, useMemo, useEffect } from 'react';
import { useKiosk } from './KioskContext';
import { kioskDocumentConfirm } from '../api';

const FIELD_CONFIG = [
    { key: 'name', label: '👤 Name / नाम', ocrKey: 'extracted_farmer_name', type: 'text', required: true, readOnly: false },
    { key: 'loan_amount', label: '💰 Loan Amount / ऋण राशि (₹)', ocrKey: 'extracted_amount', type: 'number', required: true, isAmount: true },
    { key: 'loan_reason', label: '📋 Purpose / उद्देश्य', ocrKey: 'extracted_loan_reason', type: 'text', required: true, isPurpose: true },
    { key: 'account_number', label: '🏦 Account Number / खाता संख्या', ocrKey: 'extracted_account_number', type: 'text', required: false },
    { key: 'ifsc', label: '🏛️ IFSC Code', ocrKey: 'extracted_ifsc', type: 'text', required: false },
    { key: 'phone_number', label: '📱 Phone / मोबाइल', ocrKey: 'extracted_phone', type: 'tel', required: false },
    { key: 'aadhaar_number', label: '🆔 Aadhaar / आधार', ocrKey: 'extracted_aadhaar_masked', type: 'text', required: false, isAadhaar: true },
    { key: 'annual_income', label: '📊 Annual Income / वार्षिक आय (₹)', ocrKey: 'extracted_annual_income', type: 'number', required: false },
    { key: 'land_ownership', label: '🌾 Land / भूमि', ocrKey: 'extracted_land_ownership', type: 'text', required: false },
];

function ConfidenceBadge({ confidence }) {
    if (confidence == null) return null;
    const pct = Math.round(confidence * 100);
    let cls = 'ocr-conf-low'; // red
    if (pct >= 80) cls = 'ocr-conf-high'; // green
    else if (pct >= 60) cls = 'ocr-conf-med'; // yellow
    return <span className={`ocr-confidence-badge ${cls}`}>{pct}%</span>;
}

/** Mask Aadhaar as user types: show only last 4 digits */
function maskAadhaarInput(value) {
    const digits = value.replace(/\D/g, '');
    if (digits.length <= 4) return digits;
    const masked = 'X'.repeat(digits.length - 4) + digits.slice(-4);
    // Format with dashes: XXXX-XXXX-1234
    if (masked.length === 12) {
        return `${masked.slice(0, 4)}-${masked.slice(4, 8)}-${masked.slice(8)}`;
    }
    return masked;
}

export default function KioskOCRConfirm() {
    const { state, dispatch } = useKiosk();
    const ocr = state.ocrData || {};
    const fieldConfs = ocr.field_confidences || {};
    const structuredFields = ocr.structured_fields || {};
    const needsReview = ocr.needs_review_fields || [];

    // ── Manual mode: activated when API returns manual_required: true ──
    const [manualMode, setManualMode] = useState(ocr.manual_required === true);

    // Update manual mode if ocrData changes
    useEffect(() => {
        if (ocr.manual_required === true) {
            setManualMode(true);
        }
    }, [ocr.manual_required]);

    // Initialize form values from OCR data (or empty for manual mode)
    const initialValues = useMemo(() => {
        const vals = {};
        FIELD_CONFIG.forEach(f => {
            if (manualMode) {
                // In manual mode, start with empty values
                vals[f.key] = '';
            } else if (f.key === 'name') {
                // OCR-extracted name takes priority over Aadhaar-verified name
                vals[f.key] = ocr[f.ocrKey] || '';
            } else if (f.key === 'loan_amount') {
                vals[f.key] = ocr.extracted_amount || ocr.ocr_extracted_amount || '';
            } else if (f.key === 'loan_reason') {
                vals[f.key] = ocr.extracted_purpose || ocr.ocr_extracted_purpose || ocr.extracted_loan_reason || '';
            } else {
                vals[f.key] = ocr[f.ocrKey] || '';
            }
        });
        return vals;
    }, [ocr, manualMode]);

    const [values, setValues] = useState(initialValues);
    const [aadhaarRaw, setAadhaarRaw] = useState(''); // Raw digits for Aadhaar
    const [attempt, setAttempt] = useState(1);
    const [loading, setLoading] = useState(false);

    // Reset form values when initialValues change
    useEffect(() => {
        setValues(initialValues);
    }, [initialValues]);

    const updateField = (key, val) => {
        setValues(prev => ({ ...prev, [key]: val }));
    };

    const handleAadhaarChange = (e) => {
        const raw = e.target.value.replace(/\D/g, '').slice(0, 12);
        setAadhaarRaw(raw);
        updateField('aadhaar_number', maskAadhaarInput(raw));
    };

    const handleConfirm = async () => {
        if (!values.loan_amount || !values.loan_reason) {
            dispatch({ type: 'SET_ERROR', error: 'Loan amount and purpose are required.' });
            return;
        }
        setLoading(true);
        dispatch({ type: 'SET_ERROR', error: null });
        try {
            await kioskDocumentConfirm(state.loanId, {
                confirmed_amount: parseFloat(values.loan_amount),
                confirmed_purpose: values.loan_reason,
                attempt_number: attempt,
                // Farmer-confirmed name from OCR review
                confirmed_name: values.name || null,
                // Structured extras
                confirmed_account_number: values.account_number || null,
                confirmed_ifsc: values.ifsc || null,
                confirmed_phone: values.phone_number || null,
                confirmed_annual_income: values.annual_income ? parseFloat(values.annual_income) : null,
                confirmed_land_ownership: values.land_ownership || null,
                confirmed_loan_reason: values.loan_reason || null,
            }, state.sessionToken);
            dispatch({ type: 'SET_OCR_CONFIRMED' });
            dispatch({
                type: 'SET_LOAN_DATA',
                amount: parseFloat(values.loan_amount),
                purpose: values.loan_reason,
            });
            dispatch({ type: 'NEXT_STEP' });
        } catch (err) {
            const msg = err.response?.data?.detail || 'Confirmation failed';
            dispatch({ type: 'SET_ERROR', error: typeof msg === 'object' ? msg.message : msg });
            setAttempt(a => a + 1);
        } finally {
            setLoading(false);
        }
    };



    const ocrEngine = ocr.ocr_engine || 'unknown';
    const ocrSource = ocr.ocr_source || ocrEngine;

    // ═══════════════════════════════════════════════════════════════
    //  MANUAL MODE — Full manual entry form
    // ═══════════════════════════════════════════════════════════════
    if (manualMode) {
        return (
            <div className="kiosk-step kiosk-ocr-confirm">
                <h2 className="kiosk-step-title">✍️ Manual Entry / मैन्युअल प्रविष्टि</h2>
                <p className="kiosk-step-subtitle">
                    OCR could not extract data automatically.
                    Please fill in all fields manually from the loan application form.
                </p>

                <div className="kiosk-manual-alert" style={{
                    background: 'rgba(255, 152, 0, 0.15)',
                    border: '1px solid rgba(255, 152, 0, 0.4)',
                    borderRadius: '8px',
                    padding: '12px 16px',
                    marginBottom: '20px',
                    color: '#ff9800',
                    fontWeight: 500,
                }}>
                    ⚠️ Automatic text recognition was not available. Please enter all details manually.
                </div>

                <div className="kiosk-ocr-results">
                    <div className="kiosk-ocr-card">
                        {FIELD_CONFIG.map(field => (
                            <div key={field.key} className="kiosk-ocr-row">
                                <label>
                                    {field.label}
                                    {field.required && <span className="required-star"> *</span>}
                                </label>

                                {field.isAadhaar ? (
                                    <div>
                                        <input
                                            id={`manual-${field.key}`}
                                            type="text"
                                            value={values[field.key]}
                                            onChange={handleAadhaarChange}
                                            className="kiosk-input"
                                            placeholder="Enter 12-digit Aadhaar (only last 4 shown)"
                                            maxLength={14}
                                        />
                                        <span className="ocr-mask-note" style={{ fontSize: '0.8em', color: '#999' }}>
                                            🔒 Only last 4 digits shown for security
                                        </span>
                                    </div>
                                ) : (
                                    <input
                                        id={`manual-${field.key}`}
                                        type={field.type}
                                        value={values[field.key]}
                                        onChange={(e) => updateField(field.key, e.target.value)}
                                        className="kiosk-input"
                                        placeholder={`Enter ${field.label.split('/')[0].replace(/[^\w\s]/g, '').trim()}`}
                                    />
                                )}
                            </div>
                        ))}
                    </div>
                </div>

                <div className="kiosk-btn-row">
                    <button
                        id="manual-submit-btn"
                        className="btn-kiosk-primary"
                        onClick={handleConfirm}
                        disabled={!values.loan_amount || !values.loan_reason || loading}
                    >
                        {loading ? '⏳ Submitting...' : '✅ Submit Manual Entry'}
                    </button>
                </div>
            </div>
        );
    }

    // ═══════════════════════════════════════════════════════════════
    //  OCR MODE — Verify extracted fields
    // ═══════════════════════════════════════════════════════════════
    return (
        <div className="kiosk-step kiosk-ocr-confirm">
            <h2 className="kiosk-step-title">🔍 Verify Scanned Data / स्कैन किया गया डेटा सत्यापित करें</h2>
            <p className="kiosk-step-subtitle">
                Please verify the information extracted from your document.
                Correct any values that don't match what you wrote.
            </p>

            {ocrSource !== 'unknown' && (
                <div className="ocr-engine-badge">
                    🤖 OCR Source: <strong>{ocrSource}</strong>
                    {ocr.ocr_fallback_used && (
                        <span style={{ marginLeft: '8px', color: '#ff9800', fontSize: '0.85em' }}>
                            ⚡ Fallback used
                        </span>
                    )}
                    {ocr.confidence_score != null && (
                        <> — Overall Confidence: <ConfidenceBadge confidence={ocr.confidence_score} /></>
                    )}
                </div>
            )}

            {needsReview.length > 0 && (
                <div className="kiosk-ocr-review-alert">
                    ⚠️ <strong>{needsReview.length} field(s)</strong> have low confidence and need manual verification.
                </div>
            )}

            <div className="kiosk-ocr-results">
                <div className="kiosk-ocr-card">
                    {FIELD_CONFIG.map(field => {
                        const conf = fieldConfs[field.key]?.confidence ??
                                     structuredFields[field.key]?.confidence ?? null;
                        const isLowConf = needsReview.includes(field.key);
                        const ocrVal = ocr[field.ocrKey] || '';

                        return (
                            <div
                                key={field.key}
                                className={`kiosk-ocr-row ${isLowConf ? 'ocr-low-confidence' : ''}`}
                                style={isLowConf ? {
                                    background: 'rgba(255, 235, 59, 0.15)',
                                    borderLeft: '3px solid #fdd835',
                                    paddingLeft: '12px',
                                } : {}}
                            >
                                <label>
                                    {field.label}
                                    {field.required && <span className="required-star"> *</span>}
                                    {conf != null && <ConfidenceBadge confidence={conf} />}
                                    {isLowConf && (
                                        <span style={{ marginLeft: '6px', fontSize: '0.75em', color: '#f9a825' }}>
                                            ⚠ Low confidence — please verify
                                        </span>
                                    )}
                                </label>

                                {ocrVal && (
                                    <div className="kiosk-ocr-extracted">
                                        OCR read: {field.isAadhaar ? ocrVal : (
                                            field.isAmount ? `₹${Number(ocrVal).toLocaleString('en-IN')}` :
                                            String(ocrVal))}
                                    </div>
                                )}

                                {field.isAadhaar ? (
                                    <div className="kiosk-ocr-value locked">
                                        {values[field.key] || 'Not detected'}
                                        <span className="ocr-mask-note">🔒 Aadhaar is masked for security</span>
                                    </div>
                                ) : (
                                    <input
                                        type={field.type}
                                        value={values[field.key]}
                                        onChange={(e) => updateField(field.key, e.target.value)}
                                        className={`kiosk-input ${isLowConf ? 'input-low-conf' : ''}`}
                                        placeholder={`Enter ${field.label.split('/')[0].replace(/[^\w\s]/g, '').trim()}`}
                                        style={isLowConf ? { borderColor: '#fdd835', borderWidth: '2px' } : {}}
                                    />
                                )}

                                {structuredFields[field.key]?.validation_error && (
                                    <div className="ocr-validation-error">
                                        ⚠️ {structuredFields[field.key].validation_error}
                                    </div>
                                )}
                            </div>
                        );
                    })}
                </div>

                {attempt > 2 && (
                    <div className="kiosk-ocr-retry-warning">
                        ⚠️ Multiple correction attempts detected. Consider requesting employee assistance.
                    </div>
                )}
            </div>

            <div className="kiosk-btn-row">
                <button
                    className="btn-kiosk-primary"
                    onClick={handleConfirm}
                    disabled={!values.loan_amount || !values.loan_reason || loading}
                >
                    {loading ? '⏳ Confirming...' : '✅ Confirm Values'}
                </button>
            </div>
        </div>
    );
}
