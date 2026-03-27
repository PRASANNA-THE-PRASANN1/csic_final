/**
 * ClerkReviewPage — Page for clerks to review pending kiosk loan applications.
 * Displays list of pending loans, detailed verification view with 5 sections,
 * accept/reject actions with verification gating and 60-second minimum review.
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
    getPendingReviewLoans,
    getReviewDetail,
    getKioskEvidence,
    getKioskPhoto,
    getKioskDocument,
    getTierInfo,
    verifyBlockchainLoan,
    clerkAcceptLoan,
    clerkRejectLoan,
} from '../api';

const REJECTION_CATEGORIES = [
    'Incomplete Documentation',
    'Suspected Fraudulent Application',
    'Farmer Information Mismatch',
    'Duplicate Application',
    'Policy Violation',
    'Other',
];

const REVIEW_MIN_SECONDS = 60;

export default function ClerkReviewPage() {
    const [loans, setLoans] = useState([]);
    const [totalLoans, setTotalLoans] = useState(0);
    const [selectedLoan, setSelectedLoan] = useState(null);
    const [detail, setDetail] = useState(null);
    const [evidence, setEvidence] = useState(null);
    const [loading, setLoading] = useState(false);
    const [actionLoading, setActionLoading] = useState(false);
    const [error, setError] = useState('');
    const [success, setSuccess] = useState('');
    const [showRejectModal, setShowRejectModal] = useState(false);
    const [rejectReason, setRejectReason] = useState('');
    const [rejectCategory, setRejectCategory] = useState('');

    // Verification state
    const [checks, setChecks] = useState({
        loan: false, document: false, biometric: false, aadhaar: false, blockchain: false,
    });
    const [tierInfo, setTierInfo] = useState(null);
    const [photoFrames, setPhotoFrames] = useState(null);
    const [photoLoading, setPhotoLoading] = useState(false);
    const [documentUrl, setDocumentUrl] = useState(null);
    const [documentLoading, setDocumentLoading] = useState(false);
    const [showDocModal, setShowDocModal] = useState(false);
    const [blockchainResult, setBlockchainResult] = useState(null);
    const [blockchainLoading, setBlockchainLoading] = useState(false);
    const [aadhaarInput, setAadhaarInput] = useState('');
    const [aadhaarMatch, setAadhaarMatch] = useState(null); // null | 'match' | 'mismatch'
    const [timeRemaining, setTimeRemaining] = useState(REVIEW_MIN_SECONDS);
    const timerRef = useRef(null);

    const completedCount = Object.values(checks).filter(Boolean).length;
    const allChecked = completedCount === 5;
    const timerExpired = timeRemaining <= 0;

    const fetchLoans = useCallback(async () => {
        setLoading(true);
        setError('');
        try {
            const res = await getPendingReviewLoans();
            setLoans(res.data.loans || []);
            setTotalLoans(res.data.total || 0);
        } catch (err) {
            setError('Failed to load pending loans.');
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        fetchLoans();
    }, [fetchLoans]);

    // Timer countdown
    useEffect(() => {
        if (selectedLoan && timeRemaining > 0) {
            timerRef.current = setInterval(() => {
                setTimeRemaining(prev => {
                    if (prev <= 1) {
                        clearInterval(timerRef.current);
                        return 0;
                    }
                    return prev - 1;
                });
            }, 1000);
        }
        return () => clearInterval(timerRef.current);
    }, [selectedLoan, timeRemaining]);

    const handleSelectLoan = async (loanId) => {
        setSelectedLoan(loanId);
        setDetail(null);
        setEvidence(null);
        setSuccess('');
        setError('');
        setChecks({ loan: false, document: false, biometric: false, aadhaar: false, blockchain: false });
        setTierInfo(null);
        setPhotoFrames(null);
        setDocumentUrl(null);
        setBlockchainResult(null);
        setAadhaarInput('');
        setAadhaarMatch(null);
        setTimeRemaining(REVIEW_MIN_SECONDS);
        try {
            const [detailRes, evidenceRes] = await Promise.all([
                getReviewDetail(loanId),
                getKioskEvidence(loanId),
            ]);
            setDetail(detailRes.data);
            setEvidence(evidenceRes.data);

            // Calculate remaining time based on server clerk_review_opened_at
            if (detailRes.data.clerk_review_opened_at) {
                const openedAt = new Date(detailRes.data.clerk_review_opened_at);
                const elapsed = (Date.now() - openedAt.getTime()) / 1000;
                setTimeRemaining(Math.max(0, Math.ceil(REVIEW_MIN_SECONDS - elapsed)));
            }

            // Fetch tier info
            if (detailRes.data.amount) {
                try {
                    const tierRes = await getTierInfo(detailRes.data.amount);
                    setTierInfo(tierRes.data);
                } catch { /* tier info optional */ }
            }
        } catch (err) {
            setError('Failed to load loan details.');
        }
    };

    const handleLoadPhoto = async () => {
        if (!selectedLoan) return;
        setPhotoLoading(true);
        try {
            const res = await getKioskPhoto(selectedLoan);
            setPhotoFrames(res.data.frames || []);
        } catch (err) {
            setError('Failed to load presence photos. Photos may not exist for demo data.');
        } finally {
            setPhotoLoading(false);
        }
    };

    const handleLoadDocument = async () => {
        if (!selectedLoan) return;
        setDocumentLoading(true);
        try {
            const res = await getKioskDocument(selectedLoan);
            const url = URL.createObjectURL(res.data);
            setDocumentUrl(url);
        } catch (err) {
            setError('Failed to load document. Document may not exist for demo data.');
        } finally {
            setDocumentLoading(false);
        }
    };

    const handleVerifyBlockchain = async () => {
        if (!selectedLoan) return;
        setBlockchainLoading(true);
        try {
            const res = await verifyBlockchainLoan(selectedLoan);
            setBlockchainResult(res.data);
        } catch (err) {
            setBlockchainResult({ verified: false, error: err.response?.data?.detail || 'Verification failed' });
        } finally {
            setBlockchainLoading(false);
        }
    };

    const handleAadhaarVerify = () => {
        if (!evidence?.presence?.aadhaar_last_four || !aadhaarInput) return;
        if (aadhaarInput === evidence.presence.aadhaar_last_four) {
            setAadhaarMatch('match');
        } else {
            setAadhaarMatch('mismatch');
        }
    };

    const toggleCheck = (key) => {
        setChecks(prev => ({ ...prev, [key]: !prev[key] }));
    };

    const handleAccept = async () => {
        if (!selectedLoan || !allChecked || !timerExpired) return;
        setActionLoading(true);
        setError('');
        try {
            await clerkAcceptLoan(selectedLoan);
            setSuccess(`Loan ${selectedLoan} accepted and forwarded for approvals.`);
            if (documentUrl) URL.revokeObjectURL(documentUrl);
            setDocumentUrl(null);
            setSelectedLoan(null);
            setDetail(null);
            setEvidence(null);
            fetchLoans();
        } catch (err) {
            const msg = err.response?.data?.detail || 'Failed to accept loan.';
            setError(typeof msg === 'object' ? JSON.stringify(msg) : msg);
        } finally {
            setActionLoading(false);
        }
    };

    const handleReject = async () => {
        if (!selectedLoan || rejectReason.length < 20 || !rejectCategory) return;
        setActionLoading(true);
        setError('');
        try {
            await clerkRejectLoan(selectedLoan, {
                reason_text: rejectReason,
                rejection_category: rejectCategory,
            });
            setSuccess(`Loan ${selectedLoan} rejected.`);
            if (documentUrl) URL.revokeObjectURL(documentUrl);
            setDocumentUrl(null);
            setSelectedLoan(null);
            setDetail(null);
            setEvidence(null);
            setShowRejectModal(false);
            setRejectReason('');
            setRejectCategory('');
            fetchLoans();
        } catch (err) {
            const msg = err.response?.data?.detail || 'Failed to reject loan.';
            setError(typeof msg === 'object' ? JSON.stringify(msg) : msg);
        } finally {
            setActionLoading(false);
        }
    };

    const handleBack = () => {
        setSelectedLoan(null);
        setDetail(null);
        setEvidence(null);
        setSuccess('');
        setError('');
        if (documentUrl) URL.revokeObjectURL(documentUrl);
    };

    const MatchBadge = ({ val1, val2, formatter }) => {
        const v1 = formatter ? formatter(val1) : String(val1 || '');
        const v2 = formatter ? formatter(val2) : String(val2 || '');
        const match = v1 === v2;
        return (
            <span className={`clerk-match-badge ${match ? 'match' : 'mismatch'}`}>
                {match ? '✓ Match' : '✗ Mismatch'}
            </span>
        );
    };

    const formatAmount = (v) => v != null ? `₹${Number(v).toLocaleString('en-IN')}` : '—';

    return (
        <div className="clerk-review-page p-4">
            <h2 className="text-xl font-bold mb-4">📋 Pending Kiosk Loan Review</h2>

            {success && (
                <div className="alert alert-success mb-3">
                    <span className="alert-icon">✅</span> {success}
                </div>
            )}
            {error && (
                <div className="alert alert-danger mb-3">
                    <span className="alert-icon">⚠️</span> {error}
                </div>
            )}

            {/* ═══ List View ═══ */}
            {!selectedLoan && (
                <div className="clerk-loan-list">
                    <div className="clerk-summary-bar">
                        <span className="badge badge-primary">{totalLoans} Pending</span>
                    </div>

                    {loading ? (
                        <div className="text-center p-4">⏳ Loading...</div>
                    ) : loans.length === 0 ? (
                        <div className="text-center p-4 text-muted">
                            No pending loans for review. All kiosk submissions have been processed.
                        </div>
                    ) : (
                        <div className="table-responsive">
                            <table className="table">
                                <thead>
                                    <tr>
                                        <th>Loan ID</th>
                                        <th>Farmer Name</th>
                                        <th>Amount (₹)</th>
                                        <th>Purpose</th>
                                        <th>Submitted</th>
                                        <th>Assisted</th>
                                        <th>Action</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {loans.map((loan) => (
                                        <tr key={loan.loan_id}>
                                            <td className="font-mono text-sm">{loan.loan_id}</td>
                                            <td>{loan.farmer_name}</td>
                                            <td className="font-bold">
                                                ₹{Number(loan.farmer_confirmed_amount || loan.amount).toLocaleString('en-IN')}
                                            </td>
                                            <td>{loan.farmer_confirmed_purpose || loan.purpose}</td>
                                            <td>{loan.kiosk_completed_at ? new Date(loan.kiosk_completed_at).toLocaleDateString() : '—'}</td>
                                            <td>
                                                {loan.assistance_session ? (
                                                    <span className="badge badge-warning" title={`${loan.assisting_employee_name} (${loan.assisting_employee_id})`}>
                                                        👤 Yes
                                                    </span>
                                                ) : (
                                                    <span className="badge badge-success">Self</span>
                                                )}
                                            </td>
                                            <td>
                                                <button
                                                    className="btn btn-sm btn-primary"
                                                    onClick={() => handleSelectLoan(loan.loan_id)}
                                                >
                                                    Review →
                                                </button>
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    )}
                </div>
            )}

            {/* ═══ Detail / Verification View ═══ */}
            {selectedLoan && detail && (
                <div className="clerk-detail-view">
                    <button className="btn btn-outline mb-3" onClick={handleBack}>
                        ← Back to List
                    </button>

                    <div className="detail-header">
                        <h3>Loan {detail.loan_id}</h3>
                        {detail.assistance_session && (
                            <span className="badge badge-warning">
                                👤 Assisted by: {detail.assisting_employee_name} ({detail.assisting_employee_id})
                            </span>
                        )}
                    </div>

                    {/* ── Progress Bar ── */}
                    <div className="clerk-progress-bar">
                        <div className="clerk-progress-label">
                            Verification Progress: <strong>{completedCount} of 5</strong> sections complete
                        </div>
                        <div className="clerk-progress-track">
                            <div className="clerk-progress-fill" style={{ width: `${(completedCount / 5) * 100}%` }} />
                        </div>
                        {!timerExpired && (
                            <div className="clerk-countdown">
                                ⏱ Minimum review time: <strong>{timeRemaining}s</strong> remaining
                            </div>
                        )}
                        {timerExpired && !allChecked && (
                            <div className="clerk-countdown clerk-countdown-done">
                                ⏱ Review time met — complete all sections to proceed
                            </div>
                        )}
                        {timerExpired && allChecked && (
                            <div className="clerk-countdown clerk-countdown-ready">
                                ✅ All verifications complete — ready to accept
                            </div>
                        )}
                    </div>

                    {/* ═══════ SECTION 1: Loan Information ═══════ */}
                    <div className={`clerk-verify-section ${checks.loan ? 'verified' : ''}`}>
                        <h4>📄 Section 1 — Loan Information & OCR Verification</h4>

                        {/* OCR Engine info */}
                        {detail.document?.ocr_engine_used && (
                            <div className="clerk-ocr-engine-info">
                                🤖 OCR Engine: <strong>{detail.document.ocr_engine_used}</strong>
                                {detail.document.ocr_confidence_score != null && (
                                    <> — Overall Confidence: <strong style={{
                                        color: detail.document.ocr_confidence_score >= 0.8 ? 'var(--glow-teal)' :
                                               detail.document.ocr_confidence_score >= 0.6 ? 'var(--glow-amber)' : '#fca5a5'
                                    }}>{(detail.document.ocr_confidence_score * 100).toFixed(0)}%</strong></>
                                )}
                                {detail.document.ocr_needs_review_fields?.length > 0 && (
                                    <> — <span style={{color: 'var(--glow-amber)'}}>
                                        ⚠️ {detail.document.ocr_needs_review_fields.length} field(s) need review
                                    </span></>
                                )}
                            </div>
                        )}

                        <div className="clerk-comparison-table">
                            <table className="table clerk-structured-ocr-table">
                                <thead>
                                    <tr>
                                        <th>Field</th>
                                        <th>OCR Extracted</th>
                                        <th>Farmer Confirmed</th>
                                        <th>Confidence</th>
                                        <th>Status</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {/* Amount */}
                                    <tr className={detail.document?.ocr_needs_review_fields?.includes('loan_amount') ? 'clerk-field-needs-review' : ''}>
                                        <td><strong>💰 Amount (₹)</strong></td>
                                        <td>{formatAmount(detail.document?.ocr_extracted_amount)}</td>
                                        <td>{formatAmount(detail.document?.farmer_confirmed_amount)}</td>
                                        <td className="ocr-conf-cell">
                                            {detail.document?.ocr_field_confidences?.loan_amount && (
                                                <span className={`ocr-confidence-badge ${
                                                    detail.document.ocr_field_confidences.loan_amount.confidence >= 0.8 ? 'ocr-conf-high' :
                                                    detail.document.ocr_field_confidences.loan_amount.confidence >= 0.6 ? 'ocr-conf-med' : 'ocr-conf-low'
                                                }`}>{Math.round(detail.document.ocr_field_confidences.loan_amount.confidence * 100)}%</span>
                                            )}
                                        </td>
                                        <td><MatchBadge val1={detail.document?.ocr_extracted_amount}
                                             val2={detail.document?.farmer_confirmed_amount}
                                             formatter={v => String(Number(v || 0))} /></td>
                                    </tr>
                                    {/* Purpose / Reason */}
                                    <tr className={detail.document?.ocr_needs_review_fields?.includes('loan_reason') ? 'clerk-field-needs-review' : ''}>
                                        <td><strong>📋 Purpose</strong></td>
                                        <td>{detail.document?.ocr_extracted_purpose || detail.document?.ocr_extracted_loan_reason || '—'}</td>
                                        <td>{detail.document?.farmer_confirmed_purpose || detail.document?.farmer_confirmed_loan_reason || '—'}</td>
                                        <td className="ocr-conf-cell">
                                            {detail.document?.ocr_field_confidences?.loan_reason && (
                                                <span className={`ocr-confidence-badge ${
                                                    detail.document.ocr_field_confidences.loan_reason.confidence >= 0.8 ? 'ocr-conf-high' :
                                                    detail.document.ocr_field_confidences.loan_reason.confidence >= 0.6 ? 'ocr-conf-med' : 'ocr-conf-low'
                                                }`}>{Math.round(detail.document.ocr_field_confidences.loan_reason.confidence * 100)}%</span>
                                            )}
                                        </td>
                                        <td><MatchBadge val1={detail.document?.ocr_extracted_purpose}
                                             val2={detail.document?.farmer_confirmed_purpose} /></td>
                                    </tr>
                                    {/* Account Number */}
                                    <tr className={detail.document?.ocr_needs_review_fields?.includes('account_number') ? 'clerk-field-needs-review' : ''}>
                                        <td><strong>🏦 Account #</strong></td>
                                        <td className="font-mono">{detail.document?.ocr_extracted_account_number || '—'}</td>
                                        <td className="font-mono">{detail.document?.farmer_confirmed_account_number || '—'}</td>
                                        <td className="ocr-conf-cell">
                                            {detail.document?.ocr_field_confidences?.account_number && (
                                                <span className={`ocr-confidence-badge ${
                                                    detail.document.ocr_field_confidences.account_number.confidence >= 0.8 ? 'ocr-conf-high' :
                                                    detail.document.ocr_field_confidences.account_number.confidence >= 0.6 ? 'ocr-conf-med' : 'ocr-conf-low'
                                                }`}>{Math.round(detail.document.ocr_field_confidences.account_number.confidence * 100)}%</span>
                                            )}
                                        </td>
                                        <td>{detail.document?.ocr_extracted_account_number && detail.document?.farmer_confirmed_account_number ?
                                            <MatchBadge val1={detail.document.ocr_extracted_account_number} val2={detail.document.farmer_confirmed_account_number} /> : '—'}</td>
                                    </tr>
                                    {/* IFSC */}
                                    <tr className={detail.document?.ocr_needs_review_fields?.includes('ifsc') ? 'clerk-field-needs-review' : ''}>
                                        <td><strong>🏛️ IFSC</strong></td>
                                        <td className="font-mono">{detail.document?.ocr_extracted_ifsc || '—'}</td>
                                        <td className="font-mono">{detail.document?.farmer_confirmed_ifsc || '—'}</td>
                                        <td className="ocr-conf-cell">
                                            {detail.document?.ocr_field_confidences?.ifsc && (
                                                <span className={`ocr-confidence-badge ${
                                                    detail.document.ocr_field_confidences.ifsc.confidence >= 0.8 ? 'ocr-conf-high' :
                                                    detail.document.ocr_field_confidences.ifsc.confidence >= 0.6 ? 'ocr-conf-med' : 'ocr-conf-low'
                                                }`}>{Math.round(detail.document.ocr_field_confidences.ifsc.confidence * 100)}%</span>
                                            )}
                                        </td>
                                        <td>{detail.document?.ocr_extracted_ifsc && detail.document?.farmer_confirmed_ifsc ?
                                            <MatchBadge val1={detail.document.ocr_extracted_ifsc} val2={detail.document.farmer_confirmed_ifsc} /> : '—'}</td>
                                    </tr>
                                    {/* Phone */}
                                    <tr className={detail.document?.ocr_needs_review_fields?.includes('phone_number') ? 'clerk-field-needs-review' : ''}>
                                        <td><strong>📱 Phone</strong></td>
                                        <td className="font-mono">{detail.document?.ocr_extracted_phone || '—'}</td>
                                        <td className="font-mono">{detail.document?.farmer_confirmed_phone || '—'}</td>
                                        <td className="ocr-conf-cell">
                                            {detail.document?.ocr_field_confidences?.phone_number && (
                                                <span className={`ocr-confidence-badge ${
                                                    detail.document.ocr_field_confidences.phone_number.confidence >= 0.8 ? 'ocr-conf-high' :
                                                    detail.document.ocr_field_confidences.phone_number.confidence >= 0.6 ? 'ocr-conf-med' : 'ocr-conf-low'
                                                }`}>{Math.round(detail.document.ocr_field_confidences.phone_number.confidence * 100)}%</span>
                                            )}
                                        </td>
                                        <td>{detail.document?.ocr_extracted_phone && detail.document?.farmer_confirmed_phone ?
                                            <MatchBadge val1={detail.document.ocr_extracted_phone} val2={detail.document.farmer_confirmed_phone} /> : '—'}</td>
                                    </tr>
                                    {/* Aadhaar (masked) */}
                                    <tr className={detail.document?.ocr_needs_review_fields?.includes('aadhaar_number') ? 'clerk-field-needs-review' : ''}>
                                        <td><strong>🆔 Aadhaar</strong></td>
                                        <td className="font-mono">{detail.document?.ocr_extracted_aadhaar_masked || '—'}</td>
                                        <td className="font-mono">—</td>
                                        <td className="ocr-conf-cell">
                                            {detail.document?.ocr_field_confidences?.aadhaar_number && (
                                                <span className={`ocr-confidence-badge ${
                                                    detail.document.ocr_field_confidences.aadhaar_number.confidence >= 0.8 ? 'ocr-conf-high' :
                                                    detail.document.ocr_field_confidences.aadhaar_number.confidence >= 0.6 ? 'ocr-conf-med' : 'ocr-conf-low'
                                                }`}>{Math.round(detail.document.ocr_field_confidences.aadhaar_number.confidence * 100)}%</span>
                                            )}
                                        </td>
                                        <td><span style={{fontSize: '0.72rem', color: 'var(--text-muted)'}}>🔒 Masked</span></td>
                                    </tr>
                                    {/* Annual Income */}
                                    <tr className={detail.document?.ocr_needs_review_fields?.includes('annual_income') ? 'clerk-field-needs-review' : ''}>
                                        <td><strong>📊 Income</strong></td>
                                        <td>{detail.document?.ocr_extracted_annual_income ? formatAmount(detail.document.ocr_extracted_annual_income) : '—'}</td>
                                        <td>{detail.document?.farmer_confirmed_annual_income ? formatAmount(detail.document.farmer_confirmed_annual_income) : '—'}</td>
                                        <td className="ocr-conf-cell">
                                            {detail.document?.ocr_field_confidences?.annual_income && (
                                                <span className={`ocr-confidence-badge ${
                                                    detail.document.ocr_field_confidences.annual_income.confidence >= 0.8 ? 'ocr-conf-high' :
                                                    detail.document.ocr_field_confidences.annual_income.confidence >= 0.6 ? 'ocr-conf-med' : 'ocr-conf-low'
                                                }`}>{Math.round(detail.document.ocr_field_confidences.annual_income.confidence * 100)}%</span>
                                            )}
                                        </td>
                                        <td>{detail.document?.ocr_extracted_annual_income && detail.document?.farmer_confirmed_annual_income ?
                                            <MatchBadge val1={detail.document.ocr_extracted_annual_income}
                                                 val2={detail.document.farmer_confirmed_annual_income}
                                                 formatter={v => String(Number(v || 0))} /> : '—'}</td>
                                    </tr>
                                    {/* Land Ownership */}
                                    <tr className={detail.document?.ocr_needs_review_fields?.includes('land_ownership') ? 'clerk-field-needs-review' : ''}>
                                        <td><strong>🌾 Land</strong></td>
                                        <td>{detail.document?.ocr_extracted_land_ownership || '—'}</td>
                                        <td>{detail.document?.farmer_confirmed_land_ownership || '—'}</td>
                                        <td className="ocr-conf-cell">
                                            {detail.document?.ocr_field_confidences?.land_ownership && (
                                                <span className={`ocr-confidence-badge ${
                                                    detail.document.ocr_field_confidences.land_ownership.confidence >= 0.8 ? 'ocr-conf-high' :
                                                    detail.document.ocr_field_confidences.land_ownership.confidence >= 0.6 ? 'ocr-conf-med' : 'ocr-conf-low'
                                                }`}>{Math.round(detail.document.ocr_field_confidences.land_ownership.confidence * 100)}%</span>
                                            )}
                                        </td>
                                        <td>{detail.document?.ocr_extracted_land_ownership && detail.document?.farmer_confirmed_land_ownership ?
                                            <MatchBadge val1={detail.document.ocr_extracted_land_ownership} val2={detail.document.farmer_confirmed_land_ownership} /> : '—'}</td>
                                    </tr>
                                </tbody>
                            </table>
                        </div>

                        <div className="clerk-info-grid">
                            <div className="clerk-info-item">
                                <span className="clerk-info-label">Farmer Name</span>
                                <span className="clerk-info-value">{detail.farmer_name}</span>
                            </div>
                            <div className="clerk-info-item">
                                <span className="clerk-info-label">Confirmed Amount</span>
                                <span className="clerk-info-value">{formatAmount(detail.amount)}</span>
                            </div>
                            <div className="clerk-info-item">
                                <span className="clerk-info-label">Approval Tier</span>
                                <span className="clerk-info-value badge badge-primary">
                                    {detail.approval_tier?.replace('_', ' ').toUpperCase() || '—'}
                                </span>
                            </div>
                            {tierInfo && (
                                <>
                                    <div className="clerk-info-item">
                                        <span className="clerk-info-label">Tier Description</span>
                                        <span className="clerk-info-value">{tierInfo.tier_description || tierInfo.tier || '—'}</span>
                                    </div>
                                    <div className="clerk-info-item">
                                        <span className="clerk-info-label">Required Approvers</span>
                                        <span className="clerk-info-value">{tierInfo.required_approvers?.join(', ') || tierInfo.approvers || '—'}</span>
                                    </div>
                                </>
                            )}
                        </div>

                        <label className="clerk-checkbox-label">
                            <input type="checkbox" checked={checks.loan} onChange={() => toggleCheck('loan')} />
                            <span>I have verified the loan information and all OCR-extracted fields</span>
                        </label>
                    </div>

                    {/* ═══════ SECTION 2: Document Verification ═══════ */}
                    <div className={`clerk-verify-section ${checks.document ? 'verified' : ''}`}>
                        <h4>📃 Section 2 — Document Verification</h4>

                        <div className="clerk-info-grid">
                            <div className="clerk-info-item">
                                <span className="clerk-info-label">Document Hash</span>
                                <code className="clerk-info-code">{detail.document?.document_hash || '—'}</code>
                            </div>
                            <div className="clerk-info-item">
                                <span className="clerk-info-label">OCR Confidence</span>
                                <span className={`clerk-info-value ${detail.document?.ocr_confidence_score >= 0.8 ? 'text-success' : 'text-warning'}`}>
                                    {detail.document?.ocr_confidence_score
                                        ? `${(detail.document.ocr_confidence_score * 100).toFixed(0)}%`
                                        : '—'}
                                </span>
                            </div>
                            <div className="clerk-info-item">
                                <span className="clerk-info-label">Upload Timestamp</span>
                                <span className="clerk-info-value">
                                    {detail.document?.document_uploaded_at
                                        ? new Date(detail.document.document_uploaded_at).toLocaleString()
                                        : '—'}
                                </span>
                            </div>
                        </div>

                        <button
                            className="btn btn-sm btn-outline"
                            onClick={handleLoadDocument}
                            disabled={documentLoading || !!documentUrl}
                        >
                            {documentLoading ? '⏳ Loading...' : documentUrl ? '✅ Document Loaded' : '📄 View Uploaded Document'}
                        </button>

                        {/* Inline document preview — shown below Section 2 */}
                        {documentUrl && (
                            <div className="clerk-inline-doc" style={{
                                marginTop: '1rem', padding: '1rem',
                                background: 'rgba(6,6,16,0.4)',
                                border: '1px solid rgba(100,216,255,0.15)',
                                borderRadius: 14,
                            }}>
                                <h5 style={{ fontSize: '0.88rem', color: '#64d8ff', marginBottom: '0.75rem' }}>
                                    📄 Uploaded Document — {selectedLoan}
                                </h5>
                                <div style={{ maxHeight: '500px', overflowY: 'auto', borderRadius: 10 }}>
                                    <img src={documentUrl} alt="Uploaded loan document" style={{ maxWidth: '100%', borderRadius: 8 }} />
                                </div>
                            </div>
                        )}

                        <label className="clerk-checkbox-label">
                            <input type="checkbox" checked={checks.document} onChange={() => toggleCheck('document')} />
                            <span>I have viewed the original document and the information matches</span>
                        </label>
                    </div>

                    {/* ═══════ SECTION 3: Biometric & Presence ═══════ */}
                    <div className={`clerk-verify-section ${checks.biometric ? 'verified' : ''}`}>
                        <h4>📍 Section 3 — Biometric & Presence Verification</h4>

                        <div className="clerk-info-grid">
                            <div className="clerk-info-item">
                                <span className="clerk-info-label">GPS Coordinates</span>
                                <span className="clerk-info-value">
                                    {detail.presence?.gps_latitude && detail.presence?.gps_longitude ? (
                                        <a
                                            href={`https://maps.google.com/?q=${detail.presence.gps_latitude},${detail.presence.gps_longitude}`}
                                            target="_blank"
                                            rel="noopener noreferrer"
                                        >
                                            📍 {detail.presence.gps_latitude.toFixed(4)}, {detail.presence.gps_longitude.toFixed(4)}
                                        </a>
                                    ) : '—'}
                                </span>
                            </div>
                            <div className="clerk-info-item">
                                <span className="clerk-info-label">GPS Captured At</span>
                                <span className="clerk-info-value">
                                    {detail.presence?.gps_captured_at
                                        ? new Date(detail.presence.gps_captured_at).toLocaleString()
                                        : '—'}
                                </span>
                            </div>
                            <div className="clerk-info-item">
                                <span className="clerk-info-label">Photo Captured At</span>
                                <span className="clerk-info-value">
                                    {detail.presence?.photo_captured_at
                                        ? new Date(detail.presence.photo_captured_at).toLocaleString()
                                        : '—'}
                                </span>
                            </div>
                            <div className="clerk-info-item">
                                <span className="clerk-info-label">Device Fingerprint</span>
                                <code className="clerk-info-code">
                                    {detail.presence?.device_fingerprint_hash
                                        ? `${detail.presence.device_fingerprint_hash.slice(0, 16)}...`
                                        : '—'}
                                </code>
                            </div>
                            <div className="clerk-info-item">
                                <span className="clerk-info-label">Face Detection</span>
                                <span className={`clerk-info-value ${detail.presence?.face_detected_client_side ? 'text-success' : 'text-danger'}`}>
                                    {detail.presence?.face_detected_client_side ? '✅ Detected' : '⚠️ Not detected'}
                                </span>
                            </div>
                            <div className="clerk-info-item">
                                <span className="clerk-info-label">Liveness Check</span>
                                <span className={`clerk-info-value ${detail.presence?.liveness_check_suspicious ? 'text-danger' : 'text-success'}`}>
                                    {detail.presence?.liveness_check_suspicious ? '🚨 SUSPICIOUS' : '✅ Passed'}
                                </span>
                            </div>
                            {detail.presence?.assisting_employee_name && (
                                <div className="clerk-info-item">
                                    <span className="clerk-info-label">Assisting Employee</span>
                                    <span className="clerk-info-value">
                                        👤 {detail.presence.assisting_employee_name} ({detail.presence.assisting_employee_id})
                                    </span>
                                </div>
                            )}
                        </div>

                        <button
                            className="btn btn-sm btn-outline"
                            onClick={handleLoadPhoto}
                            disabled={photoLoading}
                        >
                            {photoLoading ? '⏳ Loading...' : '📷 View Presence Photos'}
                        </button>

                        {photoFrames && photoFrames.length > 0 && (
                            <div className="clerk-photo-grid">
                                {photoFrames.map((frame, idx) => (
                                    <div key={idx} className="clerk-photo-frame">
                                        <img
                                            src={`data:image/jpeg;base64,${frame.data}`}
                                            alt={`Frame ${frame.frame_number}`}
                                        />
                                        <span>Frame {frame.frame_number}</span>
                                    </div>
                                ))}
                            </div>
                        )}

                        <label className="clerk-checkbox-label">
                            <input type="checkbox" checked={checks.biometric} onChange={() => toggleCheck('biometric')} />
                            <span>I have verified the farmer's physical presence evidence</span>
                        </label>
                    </div>

                    {/* ═══════ SECTION 4: Aadhaar Verification ═══════ */}
                    <div className={`clerk-verify-section ${checks.aadhaar ? 'verified' : ''}`}>
                        <h4>🆔 Section 4 — Aadhaar Verification</h4>

                        <div className="clerk-info-grid">
                            <div className="clerk-info-item">
                                <span className="clerk-info-label">Aadhaar-Verified Name</span>
                                <span className="clerk-info-value">{detail.presence?.aadhaar_verified_name || '—'}</span>
                            </div>
                            <div className="clerk-info-item">
                                <span className="clerk-info-label">Aadhaar OTP Verified</span>
                                <span className={`clerk-info-value ${detail.presence?.aadhaar_otp_verified ? 'text-success' : 'text-danger'}`}>
                                    {detail.presence?.aadhaar_otp_verified ? '✅ Yes' : '❌ No'}
                                </span>
                            </div>
                            <div className="clerk-info-item">
                                <span className="clerk-info-label">Verified At</span>
                                <span className="clerk-info-value">
                                    {detail.presence?.aadhaar_verified_at
                                        ? new Date(detail.presence.aadhaar_verified_at).toLocaleString()
                                        : '—'}
                                </span>
                            </div>
                            <div className="clerk-info-item">
                                <span className="clerk-info-label">System Last 4 Digits</span>
                                <span className="clerk-info-value font-mono">
                                    XXXX-XXXX-{evidence?.presence?.aadhaar_last_four || '****'}
                                </span>
                            </div>
                            <div className="clerk-info-item">
                                <span className="clerk-info-label">Mobile Last 4 (OTP)</span>
                                <span className="clerk-info-value font-mono">
                                    {evidence?.otp_records?.find(r => r.otp_type === 'aadhaar_auth')?.mobile_last_four || '—'}
                                </span>
                            </div>
                        </div>

                        <div className="clerk-aadhaar-verify">
                            <label className="clerk-info-label">Enter Aadhaar last 4 digits from physical form:</label>
                            <div className="clerk-aadhaar-input-row">
                                <input
                                    type="text"
                                    className="form-control"
                                    maxLength={4}
                                    placeholder="e.g. 4521"
                                    value={aadhaarInput}
                                    onChange={(e) => {
                                        setAadhaarInput(e.target.value.replace(/\D/g, ''));
                                        setAadhaarMatch(null);
                                    }}
                                    style={{ width: '120px' }}
                                />
                                <button
                                    className="btn btn-sm btn-primary"
                                    onClick={handleAadhaarVerify}
                                    disabled={aadhaarInput.length !== 4}
                                >
                                    Verify Match
                                </button>
                                {aadhaarMatch === 'match' && (
                                    <span className="clerk-match-badge match">✓ Aadhaar Match</span>
                                )}
                                {aadhaarMatch === 'mismatch' && (
                                    <span className="clerk-match-badge mismatch">✗ Aadhaar MISMATCH — FLAG FOR REVIEW</span>
                                )}
                            </div>
                        </div>

                        <label className="clerk-checkbox-label">
                            <input type="checkbox" checked={checks.aadhaar} onChange={() => toggleCheck('aadhaar')} />
                            <span>I have verified the Aadhaar details against the physical form</span>
                        </label>
                    </div>

                    {/* ═══════ SECTION 5: Blockchain Integrity ═══════ */}
                    <div className={`clerk-verify-section ${checks.blockchain ? 'verified' : ''}`}>
                        <h4>🔗 Section 5 — Blockchain Integrity Verification</h4>

                        <div className="clerk-info-grid">
                            <div className="clerk-info-item">
                                <span className="clerk-info-label">Kiosk Phase Anchor Hash</span>
                                <code className="clerk-info-code">{detail.kiosk_phase_anchor_hash || '—'}</code>
                            </div>
                            <div className="clerk-info-item">
                                <span className="clerk-info-label">Kiosk Completed</span>
                                <span className="clerk-info-value">
                                    {detail.kiosk_completed_at
                                        ? new Date(detail.kiosk_completed_at).toLocaleString()
                                        : '—'}
                                </span>
                            </div>
                        </div>

                        <button
                            className="btn btn-sm btn-outline"
                            onClick={handleVerifyBlockchain}
                            disabled={blockchainLoading}
                        >
                            {blockchainLoading ? '⏳ Verifying...' : '🔗 Verify Chain Integrity'}
                        </button>

                        {blockchainResult && (
                            <div className={`clerk-blockchain-result ${blockchainResult.verified || blockchainResult.chain_valid ? 'valid' : 'invalid'}`}>
                                {blockchainResult.verified || blockchainResult.chain_valid ? (
                                    <>
                                        <span>✅ <strong>Blockchain anchor intact — data has not been tampered since farmer submission.</strong></span>
                                        {blockchainResult.block_number && (
                                            <div style={{ marginTop: '0.5rem', fontSize: '0.78rem', opacity: 0.85 }}>
                                                Block #{blockchainResult.block_number}
                                                {blockchainResult.anchored_at && ` — Anchored: ${new Date(blockchainResult.anchored_at).toLocaleString()}`}
                                            </div>
                                        )}
                                    </>
                                ) : (
                                    <span>🚨 <strong>Tamper detected — do not accept this application, contact IT immediately.</strong> {blockchainResult.error || ''}</span>
                                )}
                            </div>
                        )}

                        <label className="clerk-checkbox-label">
                            <input type="checkbox" checked={checks.blockchain} onChange={() => toggleCheck('blockchain')} />
                            <span>I have verified the blockchain integrity</span>
                        </label>
                    </div>

                    {/* ═══ Action Buttons ═══ */}
                    <div className="clerk-actions">
                        <button
                            className="btn btn-success btn-lg"
                            onClick={handleAccept}
                            disabled={!allChecked || !timerExpired || actionLoading}
                            title={
                                !allChecked
                                    ? `Complete all 5 verification sections (${completedCount}/5 done)`
                                    : !timerExpired
                                        ? `Wait ${timeRemaining}s for minimum review time`
                                        : 'Accept and forward for approval'
                            }
                        >
                            {actionLoading
                                ? '⏳ Processing...'
                                : !allChecked
                                    ? `✅ Accept (${completedCount}/5 verified)`
                                    : !timerExpired
                                        ? `✅ Accept (${timeRemaining}s remaining)`
                                        : '✅ Accept & Forward for Approval'}
                        </button>
                        <button
                            className="btn btn-danger btn-lg"
                            onClick={() => setShowRejectModal(true)}
                            disabled={actionLoading}
                        >
                            ❌ Reject Application
                        </button>
                    </div>
                </div>
            )}

            {/* Document modal removed — now shown inline below Section 2 */}

            {/* ═══ Reject Modal ═══ */}
            {showRejectModal && (
                <div className="modal-overlay" onClick={() => setShowRejectModal(false)}>
                    <div className="modal-content" onClick={(e) => e.stopPropagation()}>
                        <h3>❌ Reject Loan {selectedLoan}</h3>
                        <div className="form-group">
                            <label>Rejection Category <span className="required">*</span></label>
                            <select
                                className="form-control"
                                value={rejectCategory}
                                onChange={(e) => setRejectCategory(e.target.value)}
                            >
                                <option value="">Select a category...</option>
                                {REJECTION_CATEGORIES.map((cat) => (
                                    <option key={cat} value={cat}>{cat}</option>
                                ))}
                            </select>
                        </div>
                        <div className="form-group">
                            <label>Reason (min 20 characters) <span className="required">*</span></label>
                            <textarea
                                className="form-control"
                                rows={4}
                                value={rejectReason}
                                onChange={(e) => setRejectReason(e.target.value)}
                                placeholder="Explain why this loan application is being rejected..."
                            />
                            <small className={rejectReason.length < 20 ? 'text-danger' : 'text-success'}>
                                {rejectReason.length}/20 characters minimum
                            </small>
                        </div>
                        <div className="modal-actions">
                            <button
                                className="btn btn-danger"
                                onClick={handleReject}
                                disabled={rejectReason.length < 20 || !rejectCategory || actionLoading}
                            >
                                {actionLoading ? '⏳...' : 'Confirm Rejection'}
                            </button>
                            <button className="btn btn-outline" onClick={() => setShowRejectModal(false)}>
                                Cancel
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
