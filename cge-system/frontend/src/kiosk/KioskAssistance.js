/**
 * KioskAssistance — Overlay shown when farmer requests employee assistance.
 */

import React from 'react';
import { useKiosk } from './KioskContext';

export default function KioskAssistance() {
    const { dispatch } = useKiosk();

    return (
        <div className="kiosk-overlay">
            <div className="kiosk-overlay-card">
                <div className="kiosk-assistance-icon">🙋</div>
                <h2>Employee Assistance Requested</h2>
                <p>
                    A bank employee has been notified and will assist you shortly.
                    Please wait at the kiosk.
                </p>
                <div className="kiosk-assistance-note">
                    ⚠️ Note: This session will be flagged as employee-assisted for auditing purposes.
                </div>
                <button
                    className="btn-kiosk-secondary"
                    onClick={() => dispatch({ type: 'SET_ASSISTANCE', value: false })}
                >
                    ← Return to Application
                </button>
            </div>
        </div>
    );
}
