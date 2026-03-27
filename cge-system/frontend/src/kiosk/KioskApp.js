/**
 * KioskApp — Main orchestrator for the kiosk flow.
 * Manages step progression and renders the appropriate step component.
 * Includes timeout overlay and assistance overlay.
 */

import React from 'react';
import { KioskProvider, useKiosk, STEPS } from './KioskContext';
import KioskStart from './KioskStart';
import KioskTerms from './KioskTerms';
import KioskAadhaarQR from './KioskAadhaarQR';
import KioskPresence from './KioskPresence';
import KioskFaceMatch from './KioskFaceMatch';
import KioskAadhaar from './KioskAadhaar';
import KioskFormInstructions from './KioskFormInstructions';
import KioskDocumentUpload from './KioskDocumentUpload';
import KioskOCRConfirm from './KioskOCRConfirm';
import KioskConsentConfirm from './KioskConsentConfirm';
import KioskReceipt from './KioskReceipt';
import KioskTimeout from './KioskTimeout';
import KioskAssistance from './KioskAssistance';

const STEP_COMPONENTS = {
    start: KioskStart,
    terms: KioskTerms,
    aadhaarQR: KioskAadhaarQR,
    presence: KioskPresence,
    faceMatch: KioskFaceMatch,
    aadhaar: KioskAadhaar,
    formReady: KioskFormInstructions,
    docUpload: KioskDocumentUpload,
    ocrConfirm: KioskOCRConfirm,
    consent: KioskConsentConfirm,
    receipt: KioskReceipt,
};

const STEP_LABELS = [
    'Start', 'Terms', 'QR Scan', 'Identity',
    'Face Match', 'Aadhaar OTP', 'Form', 'Document',
    'Confirm', 'Consent', 'Receipt'
];

function StepProgress({ current }) {
    return (
        <div className="kiosk-progress">
            {STEP_LABELS.map((label, i) => (
                <div
                    key={i}
                    className={`kiosk-progress-step ${i < current ? 'done' : ''} ${i === current ? 'active' : ''}`}
                >
                    <div className="kiosk-progress-dot">
                        {i < current ? '✓' : i + 1}
                    </div>
                    <span className="kiosk-progress-label">{label}</span>
                </div>
            ))}
        </div>
    );
}

function KioskInner() {
    const { state } = useKiosk();
    const stepName = STEPS[state.step];
    const StepComponent = STEP_COMPONENTS[stepName];

    if (state.expired) {
        return (
            <div className="kiosk-container">
                <div className="kiosk-expired">
                    <div className="kiosk-expired-icon">⏰</div>
                    <h2>Session Expired</h2>
                    <p>Your session has timed out due to inactivity.</p>
                    <p>Please ask the bank employee to start a new session.</p>
                    <button
                        className="btn-kiosk-primary"
                        onClick={() => window.location.reload()}
                    >
                        Start New Session
                    </button>
                </div>
            </div>
        );
    }

    return (
        <div className="kiosk-container">
            <header className="kiosk-header">
                <div className="kiosk-brand">
                    <span className="kiosk-brand-icon">🏦</span>
                    <div>
                        <h1 className="kiosk-brand-title">CGE Banking System</h1>
                        <span className="kiosk-brand-sub">Loan Application Kiosk</span>
                    </div>
                </div>
                {state.sessionToken && state.step > 0 && state.step < 10 && (
                    <StepProgress current={state.step} />
                )}
            </header>

            <div className="kiosk-body">
                {state.error && (
                    <div className="kiosk-error">
                        <span>⚠️</span> {state.error}
                    </div>
                )}
                {StepComponent && <StepComponent />}
            </div>

            {state.showTimeout && <KioskTimeout />}
            {state.assistanceRequested && <KioskAssistance />}
        </div>
    );
}

export default function KioskApp() {
    return (
        <KioskProvider>
            <KioskInner />
        </KioskProvider>
    );
}
