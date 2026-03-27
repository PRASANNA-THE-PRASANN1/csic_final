/**
 * ApprovalPage.js – Manager approval queue with CBS validation (§5.5).
 * §5.5 — CBS Validation button after approvals complete.
 * §5.8 — Accessibility: aria-labels, role="alert", symbol-based indicators.
 */

import React, { useState, useEffect, useCallback } from 'react';
import { getLoans, getLoan, getApprovals, createApproval, managerRejectLoan, disbursementRejectLoan, auditLoan, validateLoanCBS, executeLoan, getReviewDetail, getKioskEvidence, getTierInfo } from '../api';
import api from '../api';
import { useAuth } from '../AuthContext';

export default function ApprovalPage() {
    const { user } = useAuth();
    const [loans, setLoans] = useState([]);
    const [selectedLoan, setSelectedLoan] = useState(null);
    const [approvals, setApprovals] = useState(null);
    const [consentDetails, setConsentDetails] = useState(null);
    const [notifications, setNotifications] = useState(null);
    const [kioskDetail, setKioskDetail] = useState(null);
    const [kioskEvidence, setKioskEvidence] = useState(null);
    const [tierInfo, setTierInfo] = useState(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');
    const [success, setSuccess] = useState('');
    const [approverForm, setApproverForm] = useState({
        approver_id: '', approver_name: '', approver_role: 'branch_manager', comments: '',
    });

    // §5.5 — CBS validation state
    const [cbsResult, setCbsResult] = useState(null);
    const [cbsLoading, setCbsLoading] = useState(false);

    // Execute loan state
    const [execResult, setExecResult] = useState(null);
    const [execLoading, setExecLoading] = useState(false);

    // Override state
    const [overrideReason, setOverrideReason] = useState('');
    const [overrideLoading, setOverrideLoading] = useState(false);

    // Manager rejection state
    const [showRejectPanel, setShowRejectPanel] = useState(false);
    const [rejectionReason, setRejectionReason] = useState('');
    const [rejectionCategory, setRejectionCategory] = useState('');
    const [rejectLoading, setRejectLoading] = useState(false);

    // Disbursement rejection state
    const [showDisbRejectPanel, setShowDisbRejectPanel] = useState(false);
    const [disbRejectionReason, setDisbRejectionReason] = useState('');
    const [disbRejectionCategory, setDisbRejectionCategory] = useState('');
    const [disbRejectLoading, setDisbRejectLoading] = useState(false);

    // 30-second mandatory review timer
    const [reviewTimerReady, setReviewTimerReady] = useState(false);
    const [reviewCountdown, setReviewCountdown] = useState(30);

    const fetchLoans = useCallback(async () => {
        try {
            const resp = await getLoans({ status: 'pending_approvals' });
            setLoans(resp.data.loans || resp.data || []);
        } catch { }
    }, []);

    useEffect(() => { fetchLoans(); }, [fetchLoans]);

    // Auto-fill approver form with logged-in user
    useEffect(() => {
        if (user) {
            setApproverForm(prev => ({
                ...prev,
                approver_id: user.user_id || '',
                approver_name: user.name || '',
                approver_role: user.role || 'branch_manager',
            }));
        }
    }, [user]);

    const selectLoan = async (loanId) => {
        setLoading(true);
        setCbsResult(null);
        setExecResult(null);
        setKioskDetail(null);
        setKioskEvidence(null);
        setTierInfo(null);
        setShowRejectPanel(false);
        setRejectionReason('');
        setRejectionCategory('');
        // Reset and start 30-second review timer
        setReviewTimerReady(false);
        setReviewCountdown(30);
        try {
            const [loanResp, appResp, auditResp, notifResp, detailResp, evidenceResp] = await Promise.all([
                getLoan(loanId), getApprovals(loanId), auditLoan(loanId),
                api.get(`/loans/${loanId}/notifications`).catch(() => ({ data: {} })),
                getReviewDetail(loanId).catch(() => ({ data: null })),
                getKioskEvidence(loanId).catch(() => ({ data: null })),
            ]);
            setSelectedLoan(loanResp.data);
            setApprovals(appResp.data);
            setConsentDetails(auditResp.data);
            setNotifications(notifResp.data);
            setKioskDetail(detailResp.data);
            setKioskEvidence(evidenceResp.data);
            // Fetch tier info
            if (loanResp.data?.amount) {
                try {
                    const tierResp = await getTierInfo(loanResp.data.amount);
                    setTierInfo(tierResp.data);
                } catch { /* optional */ }
            }
        } catch { }
        setLoading(false);
        // Start 30-second countdown
        const timer = setInterval(() => {
            setReviewCountdown(prev => {
                if (prev <= 1) {
                    clearInterval(timer);
                    setReviewTimerReady(true);
                    return 0;
                }
                return prev - 1;
            });
        }, 1000);
    };

    const handleApprove = async () => {
        if (!selectedLoan) return;
        setLoading(true);
        setError('');
        setSuccess('');
        try {
            await createApproval(selectedLoan.loan_id, { ...approverForm });
            setSuccess('✅ Approval recorded successfully!');
            await selectLoan(selectedLoan.loan_id);
            fetchLoans();
        } catch (e) {
            const detail = e.response?.data?.detail;
            if (typeof detail === 'object') {
                setError(Array.isArray(detail) ? detail.map(d => d.msg || JSON.stringify(d)).join('; ') : JSON.stringify(detail));
            } else {
                setError(detail || 'Approval failed');
            }
        }
        setLoading(false);
    };

    // §5.5 — CBS validation handler
    const handleCBSValidation = async () => {
        if (!selectedLoan) return;
        setCbsLoading(true);
        setError('');
        try {
            const res = await validateLoanCBS(selectedLoan.loan_id);
            setCbsResult(res.data);
            setSuccess('✅ CBS validation completed');
            await selectLoan(selectedLoan.loan_id);
        } catch (e) {
            setError(e.response?.data?.detail || 'CBS validation failed');
        }
        setCbsLoading(false);
    };

    // Execute loan handler
    const handleExecute = async () => {
        if (!selectedLoan) return;
        setExecLoading(true);
        setError('');
        try {
            const res = await executeLoan(selectedLoan.loan_id);
            setExecResult(res.data);
            setSuccess('✅ Loan executed and anchored on blockchain!');
            await selectLoan(selectedLoan.loan_id);
            fetchLoans();
        } catch (e) {
            setError(e.response?.data?.detail || 'Execution failed');
        }
        setExecLoading(false);
    };

    // Manager rejection handler
    const handleReject = async () => {
        if (!selectedLoan) return;
        setRejectLoading(true);
        setError('');
        setSuccess('');
        try {
            await managerRejectLoan(selectedLoan.loan_id, {
                rejection_reason: rejectionReason,
                rejection_category: rejectionCategory,
            });
            setSuccess('🛑 Loan application rejected. The rejection has been cryptographically signed and recorded.');
            setShowRejectPanel(false);
            setRejectionReason('');
            setRejectionCategory('');
            setSelectedLoan(null);
            fetchLoans();
        } catch (e) {
            const detail = e.response?.data?.detail;
            setError(typeof detail === 'object' ? JSON.stringify(detail) : (detail || 'Rejection failed'));
        }
        setRejectLoading(false);
    };

    // Disbursement rejection handler
    const handleDisbursementReject = async () => {
        if (!selectedLoan) return;
        setDisbRejectLoading(true);
        setError('');
        setSuccess('');
        try {
            await disbursementRejectLoan(selectedLoan.loan_id, {
                rejection_reason: disbRejectionReason,
                rejection_category: disbRejectionCategory,
            });
            setSuccess('🛑 Loan rejected at disbursement stage. The rejection has been cryptographically signed and recorded.');
            setShowDisbRejectPanel(false);
            setDisbRejectionReason('');
            setDisbRejectionCategory('');
            setSelectedLoan(null);
            fetchLoans();
        } catch (e) {
            const detail = e.response?.data?.detail;
            setError(typeof detail === 'object' ? JSON.stringify(detail) : (detail || 'Disbursement rejection failed'));
        }
        setDisbRejectLoading(false);
    };

    // Override request handler (CEO only)
    const handleOverride = async () => {
        if (!selectedLoan || !overrideReason) return;
        setOverrideLoading(true);
        setError('');
        try {
            await api.post(`/loans/${selectedLoan.loan_id}/override?reason=${encodeURIComponent(overrideReason)}`);
            setSuccess('✅ Override request created — pending auditor co-sign');
            setOverrideReason('');
        } catch (e) {
            setError(e.response?.data?.detail || 'Override request failed');
        }
        setOverrideLoading(false);
    };

    const statusColor = (status) => {
        if (status === 'anchored') return 'badge-success';
        if (status === 'executed') return 'badge-info';
        if (status === 'manager_rejected' || status === 'disbursement_rejected') return 'badge-error';
        return 'badge-warning';
    };

    return (
        <div className="clerk-review-page">
            <h2>⚡ Loan Approval Queue</h2>

            {error && <div className="alert alert-error" role="alert">⚠ {error}</div>}
            {success && <div className="alert alert-success" role="alert" aria-live="polite">{success}</div>}

            {/* Loan List */}
            {loans.length === 0 && !loading && (
                <p style={{ textAlign: 'center', padding: 20, color: 'var(--text-muted)' }}>
                    No loans in queue
                </p>
            )}
            {loans.map((loan) => (
                <React.Fragment key={loan.loan_id}>
                <div
                    className={`loan-card ${selectedLoan?.loan_id === loan.loan_id ? 'selected' : ''}`}
                    onClick={() => selectLoan(loan.loan_id)}
                    role="button"
                    tabIndex={0}
                    aria-label={`Select loan ${loan.loan_id} for ${loan.farmer_name}`}
                    onKeyDown={(e) => e.key === 'Enter' && selectLoan(loan.loan_id)}
                >
                    <div className="loan-card-row">
                        <div>
                            <span className="loan-card-farmer">{loan.farmer_name}</span>
                            <span style={{ color: 'var(--text-muted)', fontSize: '0.85rem', marginLeft: 6 }}>({loan.farmer_id})</span>
                        </div>
                        <div style={{ textAlign: 'right' }}>
                            <span className="loan-card-amount">₹{loan.amount?.toLocaleString('en-IN')}</span>
                        </div>
                    </div>
                    <div className="loan-card-row">
                        <div>
                            <span className="loan-card-id">{loan.loan_id}</span>
                            <span className="loan-card-purpose"> · {loan.purpose}</span>
                        </div>
                        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                            <span className="badge badge-gold">{loan.approval_tier}</span>
                            <span className={`badge ${statusColor(loan.status)}`}>
                                {loan.status === 'anchored' ? '✓ ' : loan.status === 'executed' ? '✓ ' : loan.status === 'manager_rejected' || loan.status === 'disbursement_rejected' ? '✗ ' : '⏳ '}
                                {loan.status?.replace(/_/g, ' ')}
                            </span>
                        </div>
                    </div>
                </div>

                {/* ═══ Inline Loan Detail — renders directly below the clicked loan ═══ */}
                {selectedLoan?.loan_id === loan.loan_id && selectedLoan && (
                <div style={{ marginTop: 'var(--space-md)', paddingTop: 'var(--space-md)', borderTop: '1px solid var(--border-default)' }}>
                    <div className="clerk-verify-section">
                        <h4>📋 Loan Details: <code>{selectedLoan.loan_id}</code></h4>
                        <div className="clerk-info-grid">
                            <div className="clerk-info-item">
                                <span className="clerk-info-label">Farmer</span>
                                <span className="clerk-info-value">{selectedLoan.farmer_name} ({selectedLoan.farmer_id})</span>
                            </div>
                            <div className="clerk-info-item">
                                <span className="clerk-info-label">Amount</span>
                                <span className="clerk-info-value" style={{ fontFamily: 'var(--font-heading)', fontSize: '1.1rem', fontWeight: 600, color: 'var(--green-mid)' }}>₹{selectedLoan.amount?.toLocaleString('en-IN')}</span>
                            </div>
                            <div className="clerk-info-item">
                                <span className="clerk-info-label">Purpose</span>
                                <span className="clerk-info-value">{selectedLoan.purpose}</span>
                            </div>
                            <div className="clerk-info-item">
                                <span className="clerk-info-label">Tenure</span>
                                <span className="clerk-info-value">{selectedLoan.tenure_months} months at {selectedLoan.interest_rate}%</span>
                            </div>
                            <div className="clerk-info-item">
                                <span className="clerk-info-label">Status</span>
                                <span className={`badge ${statusColor(selectedLoan.status)}`}>
                                    {selectedLoan.status?.replace(/_/g, ' ')}
                                </span>
                            </div>
                            <div className="clerk-info-item">
                                <span className="clerk-info-label">Hash</span>
                                <code className="clerk-info-code">{selectedLoan.loan_hash?.slice(0, 32)}...</code>
                            </div>
                        </div>
                    </div>

                    {/* 🛡️ Farmer Consent Verification — Full Kiosk Evidence */}
                    <div className="clerk-verify-section" style={{ marginTop: 'var(--space-sm)' }}>
                        <h4>🛡️ Farmer Consent & Kiosk Verification</h4>

                        {/* Clerk Verification Status */}
                        {(() => {
                            const meta = selectedLoan.metadata_json ? (typeof selectedLoan.metadata_json === 'string' ? JSON.parse(selectedLoan.metadata_json) : selectedLoan.metadata_json) : {};
                            const clerkComplete = meta.clerk_verification_complete;
                            const clerkTs = meta.clerk_verification_timestamp;
                            const clerkUserId = meta.clerk_user_id || selectedLoan.clerk_reviewed_by;
                            return (
                                <div className={`clerk-blockchain-result ${clerkComplete ? 'valid' : ''}`}
                                     style={!clerkComplete ? { background: 'var(--status-warning-bg)', border: '1px solid var(--gold-pale)', color: 'var(--status-warning)' } : {}}>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                                        <span style={{ fontSize: '1.2rem' }}>{clerkComplete ? '✅' : '⏳'}</span>
                                        <strong>
                                            {clerkComplete ? 'Clerk Verification Complete (5/5 sections)' : 'Clerk Verification Pending'}
                                        </strong>
                                    </div>
                                    {clerkComplete && (
                                        <div style={{ fontSize: '0.82rem', lineHeight: 1.8 }}>
                                            Verified by: <strong>{clerkUserId}</strong>
                                            {clerkTs && <> · {new Date(clerkTs).toLocaleString()}</>}
                                            {selectedLoan.clerk_accepted_at && <> · Accepted: {new Date(selectedLoan.clerk_accepted_at).toLocaleString()}</>}
                                        </div>
                                    )}
                                </div>
                            );
                        })()}

                        {/* Quick Status Cards */}
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 10, marginTop: 12 }} role="region" aria-label="Verification status">
                            {(() => {
                                const aadhaarOk = kioskDetail?.presence?.aadhaar_otp_verified;
                                const faceOk = kioskDetail?.presence?.face_detected_client_side;
                                const livenessOk = kioskDetail?.presence && !kioskDetail.presence.liveness_check_suspicious;
                                const docOk = kioskDetail?.document?.document_hash;
                                const anchorOk = kioskDetail?.kiosk_phase_anchor_hash;
                                const Card = ({ ok, label }) => (
                                    <div className={`clerk-blockchain-result ${ok ? 'valid' : ''}`}
                                         style={{ textAlign: 'center', padding: '14px 12px', ...(ok ? {} : { background: 'var(--status-warning-bg)', border: '1px solid var(--gold-pale)', color: 'var(--status-warning)' }) }}>
                                        <span style={{ fontSize: '1.4rem', display: 'block', marginBottom: 4 }}>{ok ? '✓' : '⏳'}</span>
                                        <span style={{ fontSize: '0.78rem', fontWeight: 500 }}>{label}</span>
                                    </div>
                                );
                                return (
                                    <>
                                        <Card ok={aadhaarOk} label={aadhaarOk ? '✓ Aadhaar OTP' : '⏳ Aadhaar'} />
                                        <Card ok={faceOk} label={faceOk ? '✓ Face Detected' : '⚠ No Face'} />
                                        <Card ok={livenessOk} label={livenessOk ? '✓ Liveness' : '🚨 Suspicious'} />
                                        <Card ok={docOk} label={docOk ? '✓ Document' : '⏳ Document'} />
                                        <Card ok={anchorOk} label={anchorOk ? '✓ Blockchain' : '⏳ Anchor'} />
                                    </>
                                );
                            })()}
                        </div>

                        {/* Detailed Kiosk Evidence */}
                        {kioskDetail && (
                            <div style={{ marginTop: 16 }}>
                                {/* Loan Info: OCR vs Confirmed */}
                                <div className="clerk-verify-section" style={{ marginBottom: 12 }}>
                                    <h4>📄 Loan Information — OCR vs Farmer Confirmed</h4>
                                    <div className="clerk-comparison-table">
                                        <table className="table">
                                            <thead>
                                                <tr>
                                                    <th>Field</th>
                                                    <th>System Extracted (OCR)</th>
                                                    <th>Farmer Confirmed</th>
                                                    <th>Status</th>
                                                </tr>
                                            </thead>
                                            <tbody>
                                                <tr>
                                                    <td><strong>Amount</strong></td>
                                                    <td>₹{Number(kioskDetail.document?.ocr_extracted_amount || 0).toLocaleString('en-IN')}</td>
                                                    <td>₹{Number(kioskDetail.document?.farmer_confirmed_amount || 0).toLocaleString('en-IN')}</td>
                                                    <td>
                                                        {String(Number(kioskDetail.document?.ocr_extracted_amount || 0)) === String(Number(kioskDetail.document?.farmer_confirmed_amount || 0))
                                                            ? <span className="clerk-match-badge match">✓ Match</span>
                                                            : <span className="clerk-match-badge mismatch">✗ Mismatch</span>}
                                                    </td>
                                                </tr>
                                                <tr>
                                                    <td><strong>Purpose</strong></td>
                                                    <td>{kioskDetail.document?.ocr_extracted_purpose || '—'}</td>
                                                    <td>{kioskDetail.document?.farmer_confirmed_purpose || '—'}</td>
                                                    <td>
                                                        {(kioskDetail.document?.ocr_extracted_purpose || '') === (kioskDetail.document?.farmer_confirmed_purpose || '')
                                                            ? <span className="clerk-match-badge match">✓ Match</span>
                                                            : <span className="clerk-match-badge mismatch">✗ Mismatch</span>}
                                                    </td>
                                                </tr>
                                            </tbody>
                                        </table>
                                    </div>
                                    <div className="clerk-info-grid" style={{ marginTop: 10 }}>
                                        <div className="clerk-info-item">
                                            <span className="clerk-info-label">Approval Tier</span>
                                            <span className="clerk-info-value">
                                                <span className="badge badge-gold">
                                                    {kioskDetail.approval_tier?.replace('_', ' ').toUpperCase() || '—'}
                                                </span>
                                            </span>
                                        </div>
                                        {tierInfo && (
                                            <div className="clerk-info-item">
                                                <span className="clerk-info-label">Required Approvers</span>
                                                <span className="clerk-info-value">{tierInfo.required_approvers?.join(', ') || tierInfo.approvers || '—'}</span>
                                            </div>
                                        )}
                                    </div>
                                </div>

                                {/* Document Integrity */}
                                <div className="clerk-verify-section" style={{ marginBottom: 12 }}>
                                    <h4>📃 Document Integrity</h4>
                                    <div className="clerk-info-grid">
                                        <div className="clerk-info-item">
                                            <span className="clerk-info-label">Document Hash</span>
                                            <code className="clerk-info-code">{kioskDetail.document?.document_hash || '—'}</code>
                                        </div>
                                        <div className="clerk-info-item">
                                            <span className="clerk-info-label">OCR Confidence</span>
                                            <span className={`clerk-info-value ${kioskDetail.document?.ocr_confidence_score >= 0.8 ? 'text-success' : 'text-warning'}`}>
                                                {kioskDetail.document?.ocr_confidence_score
                                                    ? `${(kioskDetail.document.ocr_confidence_score * 100).toFixed(0)}%`
                                                    : '—'}
                                            </span>
                                        </div>
                                        <div className="clerk-info-item">
                                            <span className="clerk-info-label">Uploaded At</span>
                                            <span className="clerk-info-value">
                                                {kioskDetail.document?.document_uploaded_at
                                                    ? new Date(kioskDetail.document.document_uploaded_at).toLocaleString()
                                                    : '—'}
                                            </span>
                                        </div>
                                    </div>
                                </div>

                                {/* Aadhaar & Identity */}
                                <div className="clerk-verify-section" style={{ marginBottom: 12 }}>
                                    <h4>🆔 Aadhaar & Identity Verification</h4>
                                    <div className="clerk-info-grid">
                                        <div className="clerk-info-item">
                                            <span className="clerk-info-label">Aadhaar Name</span>
                                            <span className="clerk-info-value">{kioskDetail.presence?.aadhaar_verified_name || '—'}</span>
                                        </div>
                                        <div className="clerk-info-item">
                                            <span className="clerk-info-label">OTP Verified</span>
                                            <span className={`clerk-info-value ${kioskDetail.presence?.aadhaar_otp_verified ? 'text-success' : 'text-danger'}`}>
                                                {kioskDetail.presence?.aadhaar_otp_verified ? '✅ Yes' : '❌ No'}
                                            </span>
                                        </div>
                                        <div className="clerk-info-item">
                                            <span className="clerk-info-label">Verified At</span>
                                            <span className="clerk-info-value">
                                                {kioskDetail.presence?.aadhaar_verified_at
                                                    ? new Date(kioskDetail.presence.aadhaar_verified_at).toLocaleString()
                                                    : '—'}
                                            </span>
                                        </div>
                                        <div className="clerk-info-item">
                                            <span className="clerk-info-label">Aadhaar (Masked)</span>
                                            <span className="clerk-info-value" style={{ fontFamily: "'Courier New', monospace" }}>
                                                XXXX-XXXX-{kioskEvidence?.presence?.aadhaar_last_four || '****'}
                                            </span>
                                        </div>
                                    </div>
                                </div>

                                {/* Biometric & Presence */}
                                <div className="clerk-verify-section" style={{ marginBottom: 12 }}>
                                    <h4>📍 Biometric & Presence Evidence</h4>
                                    <div className="clerk-info-grid">
                                        <div className="clerk-info-item">
                                            <span className="clerk-info-label">GPS Coordinates</span>
                                            <span className="clerk-info-value">
                                                {kioskDetail.presence?.gps_latitude && kioskDetail.presence?.gps_longitude ? (
                                                    <a href={`https://maps.google.com/?q=${kioskDetail.presence.gps_latitude},${kioskDetail.presence.gps_longitude}`}
                                                       target="_blank" rel="noopener noreferrer">
                                                        📍 {kioskDetail.presence.gps_latitude.toFixed(4)}, {kioskDetail.presence.gps_longitude.toFixed(4)}
                                                    </a>
                                                ) : '—'}
                                            </span>
                                        </div>
                                        <div className="clerk-info-item">
                                            <span className="clerk-info-label">Photo Captured</span>
                                            <span className="clerk-info-value">
                                                {kioskDetail.presence?.photo_captured_at
                                                    ? new Date(kioskDetail.presence.photo_captured_at).toLocaleString()
                                                    : '—'}
                                            </span>
                                        </div>
                                        <div className="clerk-info-item">
                                            <span className="clerk-info-label">Face Detection</span>
                                            <span className={`clerk-info-value ${kioskDetail.presence?.face_detected_client_side ? 'text-success' : 'text-danger'}`}>
                                                {kioskDetail.presence?.face_detected_client_side ? '✅ Detected' : '⚠️ Not detected'}
                                            </span>
                                        </div>
                                        <div className="clerk-info-item">
                                            <span className="clerk-info-label">Liveness Check</span>
                                            <span className={`clerk-info-value ${kioskDetail.presence?.liveness_check_suspicious ? 'text-danger' : 'text-success'}`}>
                                                {kioskDetail.presence?.liveness_check_suspicious ? '🚨 SUSPICIOUS' : '✅ Passed'}
                                            </span>
                                        </div>
                                        <div className="clerk-info-item">
                                            <span className="clerk-info-label">Device Fingerprint</span>
                                            <code className="clerk-info-code">
                                                {kioskDetail.presence?.device_fingerprint_hash
                                                    ? `${kioskDetail.presence.device_fingerprint_hash.slice(0, 20)}...`
                                                    : '—'}
                                            </code>
                                        </div>
                                        {kioskDetail.assistance_session && (
                                            <div className="clerk-info-item">
                                                <span className="clerk-info-label">Assisting Employee</span>
                                                <span className="clerk-info-value">
                                                    👤 {kioskDetail.assisting_employee_name} ({kioskDetail.assisting_employee_id})
                                                </span>
                                            </div>
                                        )}
                                    </div>
                                </div>

                                {/* Blockchain Anchor */}
                                <div className="clerk-verify-section" style={{ marginBottom: 12 }}>
                                    <h4>🔗 Blockchain Anchor</h4>
                                    <div className="clerk-info-grid">
                                        <div className="clerk-info-item">
                                            <span className="clerk-info-label">Kiosk Phase Hash</span>
                                            <code className="clerk-info-code">{kioskDetail.kiosk_phase_anchor_hash || '—'}</code>
                                        </div>
                                        <div className="clerk-info-item">
                                            <span className="clerk-info-label">Kiosk Completed</span>
                                            <span className="clerk-info-value">
                                                {kioskDetail.kiosk_completed_at
                                                    ? new Date(kioskDetail.kiosk_completed_at).toLocaleString()
                                                    : '—'}
                                            </span>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        )}
                    </div>

                    {/* Existing Approvals */}
                    {approvals && approvals.approvals?.length > 0 && (
                        <div style={{ marginTop: 'var(--space-md)' }}>
                            <h4 style={{ marginBottom: 'var(--space-sm)' }}>📝 Existing Approvals</h4>
                            {approvals.approvals.map((a, i) => (
                                <div key={i} className="clerk-blockchain-result valid" style={{ marginBottom: 6 }}>
                                    ✓ <strong>{a.approver_role?.replace('_', ' ')}</strong>: {a.approver_name} ({a.approver_id})
                                    {a.comments && <span style={{ color: 'var(--text-muted)' }}> – "{a.comments}"</span>}
                                </div>
                            ))}
                        </div>
                    )}

                    {/* Missing Approvals */}
                    {approvals?.missing_approvals?.length > 0 && (
                        <div style={{ marginTop: 'var(--space-sm)' }}>
                            <h4 style={{ color: 'var(--status-warning)', marginBottom: 'var(--space-sm)' }}>⏳ Missing Approvals</h4>
                            {approvals.missing_approvals.map((item, i) => (
                                <span key={i} className="badge badge-warning" style={{ marginRight: 6 }}>
                                    {typeof item === 'object' ? item.role : item}
                                </span>
                            ))}
                        </div>
                    )}

                    {/* Approval Form + Reject Button */}
                    {approvals?.missing_approvals?.length > 0 && selectedLoan.status === 'pending_approvals' && (
                        <div className="clerk-verify-section" style={{ marginTop: 'var(--space-md)' }}>
                            <h4>🖊️ Submit Approval</h4>

                            {/* 30-second review timer notice */}
                            {!reviewTimerReady && (
                                <div className="clerk-blockchain-result" style={{ background: 'var(--status-warning-bg)', border: '1px solid var(--gold-pale)', color: 'var(--status-warning)', textAlign: 'center', marginBottom: 14 }} role="alert" aria-live="polite">
                                    ⏳ Please review the loan record before acting. Actions enabled in <strong>{reviewCountdown}s</strong>
                                </div>
                            )}

                            <div className="form-group">
                                <label className="form-label">Approver ID</label>
                                <input className="form-input" value={approverForm.approver_id} onChange={(e) => setApproverForm({ ...approverForm, approver_id: e.target.value })} placeholder="e.g. EMP101" aria-label="Approver ID" />
                            </div>

                            <div className="form-group">
                                <label className="form-label">Approver Name</label>
                                <input className="form-input" value={approverForm.approver_name} onChange={(e) => setApproverForm({ ...approverForm, approver_name: e.target.value })} placeholder="e.g. Suresh Kumar" aria-label="Approver name" />
                            </div>

                            <div className="form-group">
                                <label className="form-label">Role</label>
                                <select className="form-input" value={approverForm.approver_role} onChange={(e) => setApproverForm({ ...approverForm, approver_role: e.target.value })} aria-label="Approver role">
                                    <option value="branch_manager">Branch Manager</option>
                                    <option value="credit_manager">Credit Manager</option>
                                    <option value="ceo">CEO</option>
                                    <option value="board_member">Board Member</option>
                                </select>
                            </div>

                            <div className="form-group">
                                <label className="form-label">Comments (optional)</label>
                                <input className="form-input" value={approverForm.comments} onChange={(e) => setApproverForm({ ...approverForm, comments: e.target.value })} placeholder="Remarks..." aria-label="Approval comments" />
                            </div>

                            {/* Approve + Reject buttons side by side */}
                            <div className="clerk-actions">
                                <button
                                    className="btn btn-primary btn-lg"
                                    style={{ flex: 1, opacity: reviewTimerReady ? 1 : 0.5, borderRadius: 'var(--radius-full)' }}
                                    onClick={handleApprove}
                                    disabled={loading || !approverForm.approver_id || !approverForm.approver_name || !reviewTimerReady}
                                    aria-label="Submit approval"
                                >
                                    {loading ? '🔄 Processing...' : '✅ Approve Loan'}
                                </button>
                                <button
                                    className="btn btn-danger btn-lg"
                                    style={{ flex: 1, opacity: reviewTimerReady ? 1 : 0.5 }}
                                    onClick={() => setShowRejectPanel(!showRejectPanel)}
                                    disabled={!reviewTimerReady}
                                    aria-label="Reject application"
                                >
                                    🛑 Reject Application
                                </button>
                            </div>

                            {/* Rejection Panel */}
                            {showRejectPanel && (
                                <div className="clerk-verify-section" style={{ marginTop: 'var(--space-md)', borderColor: 'var(--status-error)' }}>
                                    <h4 style={{ color: 'var(--status-error)' }}>🛑 Manager Rejection Panel</h4>

                                    <div className="form-group">
                                        <label className="form-label">Rejection Reason (minimum 30 characters)</label>
                                        <textarea
                                            className="form-input"
                                            style={{ minHeight: 100, resize: 'vertical' }}
                                            value={rejectionReason}
                                            onChange={(e) => setRejectionReason(e.target.value)}
                                            placeholder="Provide a detailed, substantive reason for rejecting this loan application..."
                                            aria-label="Rejection reason"
                                        />
                                        <div style={{ fontSize: '0.75rem', textAlign: 'right', color: rejectionReason.length >= 30 ? 'var(--status-success)' : 'var(--status-warning)' }}>
                                            {rejectionReason.length}/30 characters {rejectionReason.length >= 30 ? '✓' : '(minimum 30)'}
                                        </div>
                                    </div>

                                    <div className="form-group">
                                        <label className="form-label">Rejection Category</label>
                                        <select className="form-input" value={rejectionCategory} onChange={(e) => setRejectionCategory(e.target.value)} aria-label="Rejection category">
                                            <option value="">— Select a category —</option>
                                            <option value="Credit Risk">Credit Risk</option>
                                            <option value="Insufficient Collateral">Insufficient Collateral</option>
                                            <option value="Policy Violation">Policy Violation</option>
                                            <option value="Duplicate Application">Duplicate Application</option>
                                            <option value="Suspicious Documentation">Suspicious Documentation</option>
                                            <option value="Incomplete Information">Incomplete Information</option>
                                            <option value="Exceeds Eligibility Limit">Exceeds Eligibility Limit</option>
                                            <option value="Other">Other</option>
                                        </select>
                                    </div>

                                    <button
                                        className="btn btn-danger btn-lg"
                                        style={{ width: '100%', opacity: (rejectionReason.length >= 30 && rejectionCategory) ? 1 : 0.4 }}
                                        onClick={handleReject}
                                        disabled={rejectLoading || rejectionReason.length < 30 || !rejectionCategory}
                                        aria-label="Confirm rejection"
                                    >
                                        {rejectLoading ? '🔄 Processing Rejection...' : '🛑 Confirm Rejection'}
                                    </button>
                                </div>
                            )}
                        </div>
                    )}

                    {/* Manager Rejected Banner */}
                    {selectedLoan.status === 'manager_rejected' && (
                        <div className="alert alert-error" style={{ marginTop: 'var(--space-md)' }} role="alert">
                            <h4 style={{ color: 'var(--status-error)', marginBottom: 10 }}>🛑 MANAGER REJECTED</h4>
                            <div style={{ lineHeight: 2 }}>
                                <strong>Rejected By:</strong> {selectedLoan.manager_rejected_by_name} ({selectedLoan.manager_rejected_by_role?.replace(/_/g, ' ')})<br />
                                <strong>Category:</strong> <span className="badge badge-error">{selectedLoan.manager_rejection_category}</span><br />
                                <strong>Reason:</strong> {selectedLoan.manager_rejection_reason}<br />
                                <strong>Rejected At:</strong> {selectedLoan.manager_rejected_at ? new Date(selectedLoan.manager_rejected_at).toLocaleString() : '—'}
                            </div>
                        </div>
                    )}

                    {/* Disbursement Rejected Banner */}
                    {selectedLoan.status === 'disbursement_rejected' && (
                        <div className="alert alert-error" style={{ marginTop: 'var(--space-md)' }} role="alert">
                            <h4 style={{ color: 'var(--status-error)', marginBottom: 10 }}>🛑 REJECTED AT DISBURSEMENT STAGE</h4>
                            <div style={{ lineHeight: 2 }}>
                                <strong>Rejected By:</strong> {selectedLoan.manager_rejected_by_name} ({selectedLoan.manager_rejected_by_role?.replace(/_/g, ' ')})<br />
                                <strong>Category:</strong> <span className="badge badge-error">{selectedLoan.manager_rejection_category}</span><br />
                                <strong>Reason:</strong> {selectedLoan.manager_rejection_reason}<br />
                                <strong>Rejected At:</strong> {selectedLoan.manager_rejected_at ? new Date(selectedLoan.manager_rejected_at).toLocaleString() : '—'}
                            </div>
                            <div style={{ marginTop: 10, padding: '8px 12px', borderRadius: 8, background: 'var(--status-error-bg)', fontSize: '0.8rem', color: 'var(--status-error)' }}>
                                ⚠️ This loan was rejected AFTER all approvals were collected and CBS validation was complete. Disbursement has been permanently blocked.
                            </div>
                        </div>
                    )}

                    {/* §5.5 — CBS Validation + Execute Loan section */}
                    {approvals?.approvals_complete && (
                        <div className="clerk-verify-section" style={{ marginTop: 'var(--space-md)' }}>
                            <h4>🏦 Post-Approval Actions</h4>

                            {/* CBS Validation Button */}
                            {!cbsResult && !selectedLoan.cbs_validated_at && (
                                <button className="btn btn-primary btn-lg" style={{ width: '100%' }} onClick={handleCBSValidation} disabled={cbsLoading} aria-label="Validate with CBS">
                                    {cbsLoading ? '🔄 Validating with CBS (180ms)...' : '🏦 Validate with CBS'}
                                </button>
                            )}

                            {/* CBS Result */}
                            {(cbsResult || selectedLoan.cbs_validated_at) && (
                                <div className="clerk-blockchain-result valid" style={{ marginTop: 16 }} aria-live="polite">
                                    <h4 style={{ margin: 0, fontSize: '0.95rem', fontWeight: 600 }}>
                                        {cbsResult?.ELIGIBILITY_STATUS === 'ELIGIBLE' || selectedLoan.cbs_validated_at ? '✓' : '⚠'} CBS Validation Result
                                    </h4>
                                    {cbsResult && (
                                        <div style={{ marginTop: 10, fontSize: '0.85rem', lineHeight: 1.8, fontFamily: "'Courier New', monospace" }}>
                                            <strong>CBS Ref ID:</strong> {cbsResult.CBS_REF_ID}<br />
                                            <strong>Eligibility:</strong>{' '}
                                            <span className={cbsResult.ELIGIBILITY_STATUS === 'ELIGIBLE' ? 'text-success' : 'text-warning'}>
                                                {cbsResult.ELIGIBILITY_STATUS === 'ELIGIBLE' ? '✓ ' : '⚠ '}{cbsResult.ELIGIBILITY_STATUS}
                                            </span><br />
                                            <strong>NPA Flag:</strong>{' '}
                                            <span className={cbsResult.NPA_FLAG === 'N' ? 'text-success' : 'text-danger'}>
                                                {cbsResult.NPA_FLAG === 'N' ? '✓ Clear' : '✗ Flagged'}
                                            </span><br />
                                            <strong>Outstanding:</strong> ₹{cbsResult.OUTSTANDING_AMT?.toLocaleString('en-IN')}<br />
                                            <strong>Existing Loans:</strong> {cbsResult.EXISTING_LOANS_COUNT}
                                        </div>
                                    )}
                                    {!cbsResult && selectedLoan.cbs_validated_at && (
                                        <p className="text-success" style={{ fontSize: '0.85rem', marginTop: 6 }}>
                                            ✓ CBS validation completed at {new Date(selectedLoan.cbs_validated_at).toLocaleString()}
                                        </p>
                                    )}
                                </div>
                            )}

                            {/* Execute Loan Button — only after CBS validated */}
                            {(cbsResult || selectedLoan.cbs_validated_at) &&
                             selectedLoan.status !== 'executed' && selectedLoan.status !== 'anchored' &&
                             !execResult && (
                                <button className="btn btn-primary btn-lg" style={{ width: '100%', marginTop: 16 }} onClick={handleExecute} disabled={execLoading} aria-label="Execute and anchor loan">
                                    {execLoading ? '🔄 Executing...' : '🔗 Execute & Anchor on Blockchain'}
                                </button>
                            )}

                            {/* Reject at Disbursement Button */}
                            {(cbsResult || selectedLoan.cbs_validated_at) &&
                             selectedLoan.status !== 'executed' && selectedLoan.status !== 'anchored' &&
                             selectedLoan.status !== 'disbursement_rejected' && (
                                <button className="btn btn-danger btn-lg" style={{ width: '100%', marginTop: 12 }} onClick={() => setShowDisbRejectPanel(!showDisbRejectPanel)} aria-label="Reject at disbursement stage">
                                    🛑 Reject at Disbursement
                                </button>
                            )}

                            {/* Disbursement Rejection Panel */}
                            {showDisbRejectPanel && (
                                <div className="clerk-verify-section" style={{ marginTop: 'var(--space-md)', borderColor: 'var(--status-error)' }}>
                                    <h4 style={{ color: 'var(--status-error)' }}>🛑 Disbursement-Level Rejection</h4>
                                    <p style={{ fontSize: '0.82rem', color: 'var(--text-muted)', marginBottom: 12 }}>
                                        This loan has completed all approvals and CBS validation. Rejecting at this stage is a critical action that will permanently block disbursement.
                                    </p>

                                    <div className="form-group">
                                        <label className="form-label">Rejection Reason (minimum 30 characters)</label>
                                        <textarea className="form-input" style={{ minHeight: 100, resize: 'vertical' }} value={disbRejectionReason} onChange={(e) => setDisbRejectionReason(e.target.value)} placeholder="Provide a detailed reason for rejecting this loan at the disbursement stage..." aria-label="Disbursement rejection reason" />
                                        <div style={{ fontSize: '0.75rem', textAlign: 'right', color: disbRejectionReason.length >= 30 ? 'var(--status-success)' : 'var(--status-warning)' }}>
                                            {disbRejectionReason.length}/30 characters {disbRejectionReason.length >= 30 ? '✓' : '(minimum 30)'}
                                        </div>
                                    </div>

                                    <div className="form-group">
                                        <label className="form-label">Rejection Category</label>
                                        <select className="form-input" value={disbRejectionCategory} onChange={(e) => setDisbRejectionCategory(e.target.value)} aria-label="Disbursement rejection category">
                                            <option value="">— Select a category —</option>
                                            <option value="Account Verification Failure">Account Verification Failure</option>
                                            <option value="Suspicious Beneficiary Account">Suspicious Beneficiary Account</option>
                                            <option value="Regulatory Compliance Issue">Regulatory Compliance Issue</option>
                                            <option value="Fraud Alert Triggered">Fraud Alert Triggered</option>
                                            <option value="CBS Validation Concern">CBS Validation Concern</option>
                                            <option value="Document Irregularity Discovered">Document Irregularity Discovered</option>
                                            <option value="Other">Other</option>
                                        </select>
                                    </div>

                                    <button
                                        className="btn btn-danger btn-lg"
                                        style={{ width: '100%', opacity: (disbRejectionReason.length >= 30 && disbRejectionCategory) ? 1 : 0.4 }}
                                        onClick={handleDisbursementReject}
                                        disabled={disbRejectLoading || disbRejectionReason.length < 30 || !disbRejectionCategory}
                                        aria-label="Confirm disbursement rejection"
                                    >
                                        {disbRejectLoading ? '🔄 Processing Rejection...' : '🛑 Confirm Disbursement Rejection'}
                                    </button>
                                </div>
                            )}

                            {/* Execution Result */}
                            {execResult && (
                                <div className="clerk-blockchain-result valid" style={{ marginTop: 16 }} aria-live="polite">
                                    <h4 style={{ margin: 0, fontWeight: 600 }}>🎉 Loan Executed & Anchored!</h4>
                                    <div style={{ marginTop: 8, fontSize: '0.82rem', fontFamily: "'Courier New', monospace" }}>
                                        Block #{execResult.blockchain_anchor?.block_number}<br />
                                        Hash: {execResult.blockchain_anchor?.transaction_hash?.slice(0, 32)}...
                                    </div>
                                </div>
                            )}
                        </div>
                    )}

                    {/* Override Request (CEO only, for blocked loans) */}
                    {user?.role === 'ceo' && selectedLoan &&
                     !['anchored', 'executed', 'fraud_confirmed'].includes(selectedLoan.status) && (
                        <div className="clerk-verify-section" style={{ marginTop: 'var(--space-md)', borderColor: 'var(--status-error)' }}>
                            <h4 style={{ color: 'var(--status-error)' }}>🔓 Override Request (CEO)</h4>
                            <div className="form-group">
                                <input className="form-input" value={overrideReason} onChange={(e) => setOverrideReason(e.target.value)} placeholder="Reason for override (min 10 characters)..." aria-label="Override reason" />
                            </div>
                            <button className="btn btn-danger btn-lg" style={{ width: '100%' }} onClick={handleOverride} disabled={overrideLoading || overrideReason.length < 10} aria-label="Submit override request">
                                {overrideLoading ? '🔄 Creating...' : '🔓 Request Override'}
                            </button>
                        </div>
                    )}
                </div>
                )}
                </React.Fragment>
            ))}
        </div>
    );
}
