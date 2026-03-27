/**
 * KioskTerms — Scrollable terms & conditions with scroll enforcement.
 * User must scroll to the bottom before the "Accept" button becomes active.
 */

import React, { useRef, useState, useCallback } from 'react';
import { useKiosk } from './KioskContext';
import { kioskAcceptTerms } from '../api';

const TERMS_TEXT = `
TERMS AND CONDITIONS — AGRICULTURAL LOAN APPLICATION

1. LOAN AGREEMENT
By proceeding with this application, you acknowledge that all information provided is true and accurate to the best of your knowledge. Any misrepresentation of facts may result in rejection of the application or legal action.

2. IDENTITY VERIFICATION
Your identity will be verified through India's Aadhaar system. An OTP will be sent to your registered mobile number. This verification is mandatory and non-transferable.

3. DOCUMENT REQUIREMENTS
You must provide a physical copy of the loan application form with your signature. This document will be scanned and verified through Optical Character Recognition (OCR). Any discrepancies between the OCR data and your declarations will be flagged for review.

4. CONSENT AND PRIVACY
Your Aadhaar data will be stored in masked form only (last 4 digits). A SHA-256 hash of your full Aadhaar number is stored for verification purposes only. Your photos, documents, and personal data are encrypted at rest using Fernet symmetric encryption.

5. LOAN TERMS
- Interest rates are determined by the loan tier based on the amount requested
- Tier 1 (up to ₹1,00,000): 7.0% per annum
- Tier 2 (₹1,00,001 to ₹5,00,000): 8.5% per annum
- Tier 3 (₹5,00,001 to ₹25,00,000): 9.5% per annum
- Loan tenure ranges from 12 to 36 months based on the amount

6. FARMER RIGHTS
- You have the right to review all loan terms before consenting
- You can request employee assistance at any point during the process
- Your consent is recorded with cryptographic proof and cannot be forged
- You will receive SMS notifications about your application status

7. ANTI-FRAUD MEASURES
This system employs multiple fraud prevention mechanisms:
- Blockchain-anchored consent records
- Biometric and location verification
- Hash integrity checks on all documents and transactions
- Role-based access controls to prevent unauthorized modifications

8. GRIEVANCE REDRESSAL
For any disputes or concerns regarding your loan application, contact:
- Branch Manager at the nearest branch office
- Toll-free helpline: 1800-XXX-XXXX
- Email: grievances@cge-bank.example.com

9. DATA RETENTION
All loan application data is retained for a minimum of 10 years as per regulatory requirements. Encrypted data may only be decrypted by authorized auditors with proper credentials.

10. GOVERNING LAW
This agreement is governed by the laws of India and subject to the jurisdiction of the courts in the district where the branch is located.

By clicking "I Accept", you acknowledge that you have read, understood, and agree to all the above terms and conditions.
`.trim();

export default function KioskTerms() {
    const { state, dispatch } = useKiosk();
    const [scrolled, setScrolled] = useState(false);
    const [loading, setLoading] = useState(false);
    const termsRef = useRef(null);

    const handleScroll = useCallback(() => {
        if (!termsRef.current) return;
        const { scrollTop, scrollHeight, clientHeight } = termsRef.current;
        if (scrollTop + clientHeight >= scrollHeight - 20) {
            setScrolled(true);
        }
    }, []);

    const handleAccept = async () => {
        setLoading(true);
        dispatch({ type: 'SET_ERROR', error: null });
        try {
            await kioskAcceptTerms(state.loanId, { scroll_completed: true }, state.sessionToken);
            dispatch({ type: 'NEXT_STEP' });
        } catch (err) {
            const msg = err.response?.data?.detail || 'Failed to accept terms';
            dispatch({ type: 'SET_ERROR', error: typeof msg === 'object' ? msg.message : msg });
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="kiosk-step kiosk-terms">
            <h2 className="kiosk-step-title">📋 Terms & Conditions</h2>
            <p className="kiosk-step-subtitle">
                Please read the following terms carefully. Scroll to the bottom to proceed.
            </p>

            <div
                className="kiosk-terms-scroll"
                ref={termsRef}
                onScroll={handleScroll}
            >
                <pre className="kiosk-terms-text">{TERMS_TEXT}</pre>
            </div>

            {!scrolled && (
                <div className="kiosk-scroll-hint">
                    <span>↓</span> Scroll down to read all terms
                </div>
            )}

            <button
                className="btn-kiosk-primary"
                onClick={handleAccept}
                disabled={!scrolled || loading}
            >
                {loading ? '⏳ Processing...' : scrolled ? '✅ I Accept the Terms' : '📜 Scroll to Continue'}
            </button>
        </div>
    );
}
