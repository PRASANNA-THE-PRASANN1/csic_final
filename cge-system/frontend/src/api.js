/**
 * Axios API client configured for the CGE backend.
 * §5.1 — Bearer JWT auth header on every request + 401 interceptor.
 */

import axios from 'axios';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

const api = axios.create({
    baseURL: `${API_BASE_URL}/api`,
    headers: { 'Content-Type': 'application/json' },
    timeout: 15000,
});

// §5.1 — Attach JWT Bearer token from localStorage on every request
api.interceptors.request.use((config) => {
    try {
        const stored = localStorage.getItem('cge_user');
        if (stored) {
            const user = JSON.parse(stored);
            if (user && user.token) {
                config.headers.Authorization = `Bearer ${user.token}`;
            }
        }
    } catch {
        // Ignore parse errors
    }
    return config;
});

// §5.1 — Response interceptor: catch 401 and auto-logout
// Skip for kiosk endpoints which use session tokens
api.interceptors.response.use(
    (response) => response,
    (error) => {
        if (error.response && error.response.status === 401) {
            const url = error.config?.url || '';
            // Don't auto-logout for kiosk endpoints
            if (!url.includes('/kiosk/')) {
                localStorage.removeItem('cge_user');
                if (window.location.pathname !== '/login') {
                    window.location.href = '/login';
                }
            }
        }
        return Promise.reject(error);
    }
);

// ── Loans ──
export const createLoan = (data) => api.post('/loans/create', data);
export const getLoan = (loanId) => api.get(`/loans/${loanId}`);
export const getLoans = (params) => api.get('/loans', { params });

// ── Farmer Consent ──
export const createFarmerConsent = (loanId, data) =>
    api.post(`/loans/${loanId}/farmer-consent`, data);

// ── Manager Approvals ──
export const createApproval = (loanId, data) =>
    api.post(`/loans/${loanId}/approve`, data);
export const getApprovals = (loanId) =>
    api.get(`/loans/${loanId}/approvals`);
export const managerRejectLoan = (loanId, data) =>
    api.post(`/loans/${loanId}/manager-reject`, data);
export const disbursementRejectLoan = (loanId, data) =>
    api.post(`/loans/${loanId}/disbursement-reject`, data);

// ── Execution ──
export const executeLoan = (loanId) =>
    api.post(`/execute-loan?loan_id=${loanId}`);

// ── Audit ──
export const auditLoan = (loanId) => api.get(`/audit/${loanId}`);

// ── Blockchain ──
export const getBlockchain = () => api.get('/blockchain/chain');
export const verifyBlockchain = () => api.get('/blockchain/verify');
export const verifyLoanBlockchain = (loanId) => api.get(`/blockchain/verify-loan/${loanId}`);

// ── Policy ──
export const getTierInfo = (amount) =>
    api.get('/policy/tier-info', { params: { amount } });

// ── Auth ──
export const loginUser = (user_id, password) =>
    api.post('/auth/login', { user_id, password });

// ── Fraud Prevention: Disbursement Consent (Type 1) ──
export const createDisbursementConsent = (loanId, data) =>
    api.post(`/loans/${loanId}/disbursement-consent`, data);

// ── Fraud Prevention: Farmer Declaration (Type 2) ──
export const createFarmerDeclaration = (data) =>
    api.post('/farmer-declaration', data);
export const getFarmerDeclaration = (declarationId) =>
    api.get(`/farmer-declaration/${declarationId}`);

// ── CBS Validation (§3.1) ──
export const validateLoanCBS = (loanId) =>
    api.post(`/cbs/validate-loan/${loanId}`);

// ── Dashboard (§3.2) ──
export const getDashboardStats = () => api.get('/dashboard/stats');

// ── Override Governance (§3.3) ──
export const createOverride = (loanId, reason) =>
    api.post(`/loans/${loanId}/override?reason=${encodeURIComponent(reason)}`);
export const cosignOverride = (loanId) =>
    api.post(`/loans/${loanId}/override/cosign`);
export const getOverrides = (loanId) =>
    api.get(`/loans/${loanId}/overrides`);

// ── Consent Certificate (§3.4) ──
export const getConsentCertificate = (loanId) =>
    api.get(`/loans/${loanId}/consent-certificate`);

// ═══════════════════════════════════════════════════
//  KIOSK SESSION API (uses X-Session-Token header)
// ═══════════════════════════════════════════════════

const kioskHeaders = (sessionToken) => ({
    headers: { 'X-Session-Token': sessionToken },
});

export const kioskStart = (employeeName, employeeId) =>
    api.post('/kiosk/start', { employee_name: employeeName, employee_id: employeeId });

export const kioskAcceptTerms = (loanId, data, token) =>
    api.post(`/kiosk/${loanId}/terms/accept`, data, kioskHeaders(token));

export const kioskCapturePhoto = (loanId, formData, token) => {
    return api.post(`/kiosk/${loanId}/presence/photo`, formData, {
        headers: {
            'X-Session-Token': token,
            'Content-Type': 'multipart/form-data',
        },
        timeout: 45000, // 45s for 5-frame photo upload + liveness data
    });
};

export const kioskAadhaarQRScan = (loanId, data, token) =>
    api.post(`/kiosk/${loanId}/aadhaar/qr-scan`, data, kioskHeaders(token));

export const kioskFaceMatch = (loanId, data, token) =>
    api.post(`/kiosk/${loanId}/face-match`, data, kioskHeaders(token));

export const kioskAadhaarInitiate = (loanId, data, token) =>
    api.post(`/kiosk/${loanId}/aadhaar/initiate`, data, kioskHeaders(token));

export const kioskAadhaarVerify = (loanId, data, token) =>
    api.post(`/kiosk/${loanId}/aadhaar/verify`, data, kioskHeaders(token));

export const kioskDocumentUpload = (loanId, file, token) => {
    const formData = new FormData();
    formData.append('file', file);
    return api.post(`/kiosk/${loanId}/document/upload`, formData, {
        headers: {
            'X-Session-Token': token,
            'Content-Type': 'multipart/form-data',
        },
    });
};

export const kioskDocumentOcr = (loanId, token) =>
    api.post(`/kiosk/${loanId}/document/ocr`, {}, kioskHeaders(token));

export const kioskDocumentConfirm = (loanId, data, token) =>
    api.post(`/kiosk/${loanId}/document/confirm`, data, kioskHeaders(token));

export const kioskConsentInitiate = (loanId, token) =>
    api.post(`/kiosk/${loanId}/consent/initiate`, {}, kioskHeaders(token));

export const kioskConsentVerify = (loanId, data, token) =>
    api.post(`/kiosk/${loanId}/consent/verify`, data, kioskHeaders(token));

export const kioskComplete = (loanId, token) =>
    api.post(`/kiosk/${loanId}/complete`, {}, kioskHeaders(token));

export const kioskRequestAssistance = (loanId, token) =>
    api.post(`/kiosk/${loanId}/assistance/request`, {}, kioskHeaders(token));

export const kioskGetStatus = (loanId, token) =>
    api.get(`/kiosk/${loanId}/status`, kioskHeaders(token));

export const kioskIvrStatus = (loanId, token) =>
    api.get(`/kiosk/${loanId}/ivr-status`, kioskHeaders(token));

// ── Clerk Kiosk Review ──
export const getPendingReviewLoans = () =>
    api.get('/loans/pending-review');

export const getKioskEvidence = (loanId) =>
    api.get(`/kiosk/${loanId}/evidence`);

export const confirmAssistance = (loanId, data) =>
    api.post(`/kiosk/${loanId}/assistance/confirm`, data);

// ── Clerk Accept/Reject ──
export const clerkAcceptLoan = (loanId) =>
    api.post(`/loans/${loanId}/clerk-accept`);

export const clerkRejectLoan = (loanId, data) =>
    api.post(`/loans/${loanId}/clerk-reject`, data);

export const getReviewDetail = (loanId) =>
    api.get(`/loans/${loanId}/review-detail`);

// ── Clerk Verification Endpoints ──
export const getKioskPhoto = (loanId) =>
    api.get(`/audit/kiosk-photo/${loanId}?format=json`);

export const getKioskDocument = (loanId) =>
    api.get(`/audit/kiosk-document/${loanId}`, { responseType: 'blob' });

export const verifyBlockchainLoan = (loanId) =>
    api.get(`/blockchain/verify-loan/${loanId}`);

// Convenience methods on api instance
api.createLoan = (data) => api.post('/loans/create', data);
api.getLoan = (loanId) => api.get(`/loans/${loanId}`);
api.createFarmerConsent = (loanId, data) => api.post(`/loans/${loanId}/farmer-consent`, data);
api.createApproval = (loanId, data) => api.post(`/loans/${loanId}/approve`, data);
api.createDisbursementConsent = (loanId, data) => api.post(`/loans/${loanId}/disbursement-consent`, data);
api.createFarmerDeclaration = (data) => api.post('/farmer-declaration', data);
api.getFarmerDeclaration = (declarationId) => api.get(`/farmer-declaration/${declarationId}`);

export default api;
