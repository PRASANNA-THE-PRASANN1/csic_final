/**
 * AuditPage.js – Audit & Verification Portal.
 * §5.6 — Consent certificate download.
 * §5.7 — Blockchain verification widget (per-loan + full chain).
 * §5.8 — Accessibility: aria-labels, role="alert", aria-live, symbol-based indicators.
 */

import React, { useState } from 'react';
import { auditLoan, executeLoan, verifyBlockchain, verifyLoanBlockchain, getConsentCertificate } from '../api';
import VerificationBadge from '../components/VerificationBadge';

export default function AuditPage() {
    const [loanId, setLoanId] = useState('');
    const [report, setReport] = useState(null);
    const [chainStatus, setChainStatus] = useState(null);
    const [loanChainStatus, setLoanChainStatus] = useState(null);
    const [loading, setLoading] = useState(false);
    const [executing, setExecuting] = useState(false);
    const [error, setError] = useState('');
    const [execResult, setExecResult] = useState(null);
    const [certificate, setCertificate] = useState(null);
    const [certLoading, setCertLoading] = useState(false);

    const handleAudit = async (e) => {
        e.preventDefault();
        if (!loanId.trim()) return;
        setLoading(true);
        setError('');
        setReport(null);
        setExecResult(null);
        setCertificate(null);
        setLoanChainStatus(null);
        try {
            const res = await auditLoan(loanId.trim());
            setReport(res.data);
        } catch (err) {
            setError(err.response?.data?.detail || 'Audit failed');
        } finally {
            setLoading(false);
        }
    };

    const handleExecute = async () => {
        setExecuting(true);
        setError('');
        try {
            const res = await executeLoan(loanId.trim());
            setExecResult(res.data);
            // Re-audit after execution
            const auditRes = await auditLoan(loanId.trim());
            setReport(auditRes.data);
        } catch (err) {
            setError(err.response?.data?.detail || 'Execution failed');
        } finally {
            setExecuting(false);
        }
    };

    // §5.7 — Full chain verification
    const handleVerifyChain = async () => {
        try {
            const res = await verifyBlockchain();
            setChainStatus(res.data);
        } catch {
            setChainStatus({ is_valid: false, error: 'Failed to verify chain' });
        }
    };

    // §5.7 — Per-loan blockchain verification
    const handleVerifyLoanChain = async () => {
        if (!loanId.trim()) return;
        try {
            const res = await verifyLoanBlockchain(loanId.trim());
            setLoanChainStatus(res.data);
        } catch (err) {
            setLoanChainStatus({ verified: false, error: err.response?.data?.detail || 'Verification failed' });
        }
    };

    // §5.6 — Download consent certificate
    const handleDownloadCertificate = async () => {
        setCertLoading(true);
        try {
            const res = await getConsentCertificate(loanId.trim());
            setCertificate(res.data);
        } catch (err) {
            setError(err.response?.data?.detail || 'Certificate generation failed');
        } finally {
            setCertLoading(false);
        }
    };

    return (
        <div className="page-container">
            <h1 className="page-title">🔍 Audit & Verification Portal</h1>
            <p className="page-desc">Verify loan integrity, detect tampering, and manage blockchain anchoring.</p>

            {/* Search */}
            <form onSubmit={handleAudit} className="search-bar">
                <input
                    value={loanId}
                    onChange={(e) => setLoanId(e.target.value)}
                    placeholder="Enter Loan ID to audit"
                    className="search-input"
                    aria-label="Loan ID for audit"
                />
                <button type="submit" className="btn btn-primary" disabled={loading} aria-label="Audit loan">
                    {loading ? '⏳' : '🔍 Audit Loan'}
                </button>
                <button type="button" onClick={handleVerifyChain} className="btn btn-outline" aria-label="Verify full blockchain chain">
                    ⛓ Verify Chain
                </button>
            </form>

            {error && <div className="alert alert-error" role="alert">{error}</div>}

            {/* Chain verification result */}
            {chainStatus && (
                <div className={`alert ${chainStatus.is_valid ? 'alert-success' : 'alert-error'}`} role="alert" aria-live="polite">
                    <h4>⛓ Blockchain Integrity</h4>
                    <p><strong>Status:</strong> {chainStatus.is_valid ? '✓ Valid' : '✗ Compromised'}</p>
                    <p><strong>Chain Length:</strong> {chainStatus.chain_length} blocks</p>
                    <p><strong>Last Block:</strong> <code>{chainStatus.last_block_hash?.slice(0, 16)}...</code></p>
                </div>
            )}

            {/* Audit Report */}
            {report && (
                <div className="audit-report">
                    <div className="audit-header">
                        <h2>Verification Report</h2>
                        <VerificationBadge status={report.overall_status === 'AUTHENTIC' ? 'valid' : 'invalid'} />
                    </div>

                    {/* Overall status */}
                    <div className={`overall-verdict ${report.overall_status === 'AUTHENTIC' ? 'verdict-valid' : 'verdict-invalid'}`}>
                        <span className="verdict-icon">{report.overall_status === 'AUTHENTIC' ? '✓' : '✗'}</span>
                        <span className="verdict-text">{report.overall_status}</span>
                    </div>

                    {/* Manager Rejected Banner */}
                    {report.loan.status === 'manager_rejected' && (
                        <div style={{
                            padding: '20px 24px', borderRadius: 14, marginBottom: 20,
                            background: 'rgba(248,113,113,0.1)',
                            border: '1px solid rgba(248,113,113,0.35)',
                        }} role="alert">
                            <h3 style={{ fontSize: '1.1rem', color: '#f87171', fontWeight: 600, marginBottom: 12 }}>
                                🛑 MANAGER REJECTED
                            </h3>
                            {report.manager_rejection ? (
                                <div style={{ fontSize: '0.88rem', lineHeight: 2, color: '#c4cdd8' }}>
                                    <strong style={{ color: '#e8edf5' }}>Rejected By:</strong>{' '}
                                    {report.manager_rejection.rejected_by_name} ({report.manager_rejection.rejected_by_role?.replace(/_/g, ' ')})<br />
                                    <strong style={{ color: '#e8edf5' }}>Category:</strong>{' '}
                                    <span style={{
                                        padding: '2px 10px', borderRadius: 8, fontSize: '0.82rem',
                                        background: 'rgba(248,113,113,0.15)', color: '#fca5a5',
                                    }}>{report.manager_rejection.rejection_category}</span><br />
                                    <strong style={{ color: '#e8edf5' }}>Reason:</strong> {report.manager_rejection.rejection_reason}<br />
                                    <strong style={{ color: '#e8edf5' }}>Rejected At:</strong>{' '}
                                    {report.manager_rejection.rejected_at ? new Date(report.manager_rejection.rejected_at).toLocaleString() : '—'}<br />
                                    <strong style={{ color: '#e8edf5' }}>Signature:</strong>{' '}
                                    <span style={{ color: report.manager_rejection.signature_valid ? '#6ee7b7' : '#fca5a5' }}>
                                        {report.manager_rejection.signature_valid ? '✓ Rejection signature valid' : '✗ Rejection signature invalid'}
                                    </span>
                                </div>
                            ) : (
                                <p style={{ color: '#fca5a5', fontSize: '0.88rem' }}>This loan was rejected by a manager. Check verification checks below for details.</p>
                            )}
                        </div>
                    )}

                    {/* Loan summary */}
                    <div className="audit-loan-summary">
                        <h3>📄 Loan Summary</h3>
                        <div className="detail-grid">
                            <div className="detail-item">
                                <span className="detail-label">Farmer</span>
                                <span className="detail-value">{report.loan.farmer_name}</span>
                            </div>
                            <div className="detail-item">
                                <span className="detail-label">Amount</span>
                                <span className="detail-value">₹{report.loan.amount?.toLocaleString('en-IN')}</span>
                            </div>
                            <div className="detail-item">
                                <span className="detail-label">Status</span>
                                <span className={`status-badge status-${report.loan.status}`}>
                                    {report.loan.status === 'anchored' ? '✓ ' : ''}
                                    {report.loan.status?.replace(/_/g, ' ')}
                                </span>
                            </div>
                            <div className="detail-item">
                                <span className="detail-label">Tier</span>
                                <span className="detail-value">{report.loan.approval_tier?.toUpperCase()}</span>
                            </div>
                        </div>
                        <div className="hash-display compact">
                            <span className="hash-header">🔑 Loan Hash</span>
                            <code className="hash-code">{report.loan.loan_hash}</code>
                        </div>
                    </div>

                    {/* Verification checks */}
                    <div className="audit-checks">
                        <h3>🔒 Verification Checks</h3>
                        {report.checks?.map((check, i) => (
                            <div key={i} className={`check-row check-${check.status}`} role="listitem">
                                <div className="check-icon">
                                    {check.status === 'valid' ? '✓' : check.status === 'missing' || check.status === 'not_anchored' ? '⏳' : '✗'}
                                </div>
                                <div className="check-content">
                                    <strong>{check.check}</strong>
                                    <span className="check-detail">
                                        {typeof check.detail === 'object' ? JSON.stringify(check.detail, null, 1) : check.detail}
                                    </span>
                                </div>
                                <VerificationBadge status={check.status} />
                            </div>
                        ))}
                    </div>

                    {/* §5.7 — Per-Loan Blockchain Verification Widget */}
                    <div className="execution-section" style={{ marginTop: 20 }}>
                        <h3>⛓ Loan Blockchain Verification</h3>
                        <button
                            className="btn btn-outline"
                            onClick={handleVerifyLoanChain}
                            style={{ marginBottom: 12, width: 'auto', padding: '10px 20px' }}
                            aria-label="Verify this loan on blockchain"
                        >
                            🔗 Verify Loan #{loanId} on Chain
                        </button>
                        {loanChainStatus && (
                            <div
                                className={`alert ${loanChainStatus.verified ? 'alert-success' : 'alert-error'}`}
                                role="alert"
                                aria-live="polite"
                            >
                                <p>
                                    <strong>Verification:</strong>{' '}
                                    {loanChainStatus.verified ? '✓ Loan is anchored and verified on blockchain' : `✗ ${loanChainStatus.error || 'Not found on chain'}`}
                                </p>
                                {loanChainStatus.block_number && (
                                    <p><strong>Block #:</strong> {loanChainStatus.block_number} · <strong>Hash:</strong> <code>{loanChainStatus.transaction_hash?.slice(0, 24)}...</code></p>
                                )}
                            </div>
                        )}
                    </div>

                    {/* §5.6 — Consent Certificate Download */}
                    <div className="execution-section" style={{ marginTop: 20 }}>
                        <h3>📜 Digital Consent Certificate</h3>
                        <p style={{ fontSize: '0.88rem', color: '#8b96a9' }}>
                            Generate a verifiable consent certificate for this loan.
                        </p>
                        {!certificate ? (
                            <button
                                className="btn btn-primary"
                                onClick={handleDownloadCertificate}
                                disabled={certLoading}
                                style={{ width: 'auto', padding: '10px 20px' }}
                                aria-label="Download consent certificate"
                            >
                                {certLoading ? '⏳ Generating...' : '📜 Generate Certificate'}
                            </button>
                        ) : (
                            <div className="alert alert-success" aria-live="polite">
                                <h4>📜 Consent Certificate</h4>
                                <div style={{ fontFamily: "'Space Mono', monospace", fontSize: '0.82rem', lineHeight: 1.8 }}>
                                    <strong>Certificate ID:</strong> {certificate.certificate_id}<br />
                                    <strong>Loan ID:</strong> {certificate.loan_id}<br />
                                    <strong>Farmer:</strong> {certificate.farmer_name} ({certificate.farmer_id})<br />
                                    <strong>Amount:</strong> ₹{certificate.amount?.toLocaleString('en-IN')}<br />
                                    <strong>Consent Method:</strong> {certificate.consent_method}<br />
                                    <strong>Consent Timestamp:</strong> {certificate.consented_at}<br />
                                    <strong>Loan Hash:</strong> <code>{certificate.loan_hash}</code><br />
                                    {certificate.blockchain_block && (
                                        <><strong>Blockchain Block #:</strong> {certificate.blockchain_block}<br /></>
                                    )}
                                    {certificate.blockchain_hash && (
                                        <><strong>Blockchain Hash:</strong> <code>{certificate.blockchain_hash?.slice(0, 32)}...</code><br /></>
                                    )}
                                    <strong>Audit URL:</strong>{' '}
                                    <a href={certificate.audit_url} target="_blank" rel="noopener noreferrer" style={{ color: '#64d8ff' }}>
                                        {certificate.audit_url}
                                    </a><br />
                                    <strong>Generated At:</strong> {certificate.generated_at}
                                </div>
                            </div>
                        )}
                    </div>

                    {/* Execute button */}
                    {report.loan.status === 'ready_for_execution' && !execResult && (
                        <div className="execution-section">
                            <h3>🚀 Execution</h3>
                            <p>All checks passed. This loan can be executed and anchored on the blockchain.</p>
                            <button
                                className="btn btn-execute btn-lg"
                                onClick={handleExecute}
                                disabled={executing}
                                aria-label="Execute and anchor on blockchain"
                            >
                                {executing ? '⏳ Executing...' : '🔗 Execute & Anchor on Blockchain'}
                            </button>
                        </div>
                    )}

                    {/* Execution result */}
                    {execResult && (
                        <div className="alert alert-success" aria-live="polite">
                            <h3>🎉 Loan Executed & Anchored!</h3>
                            <p><strong>Block Number:</strong> {execResult.blockchain_anchor?.block_number}</p>
                            <p><strong>Transaction Hash:</strong> <code>{execResult.blockchain_anchor?.transaction_hash}</code></p>
                            <p><strong>Consent Hash:</strong> <code>{execResult.blockchain_anchor?.consent_hash}</code></p>
                        </div>
                    )}

                    <p className="audit-timestamp">Verified at: {report.verified_at}</p>
                </div>
            )}
        </div>
    );
}
