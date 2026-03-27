/**
 * KioskTimeout — Warning modal shown before session expiry.
 */

import React from 'react';
import { useKiosk } from './KioskContext';

export default function KioskTimeout() {
    const { dispatch, onActivity } = useKiosk();

    const handleContinue = () => {
        onActivity();
        dispatch({ type: 'HIDE_TIMEOUT' });
    };

    return (
        <div className="kiosk-overlay">
            <div className="kiosk-overlay-card kiosk-timeout-card">
                <div className="kiosk-timeout-icon">⏰</div>
                <h2>Session Timing Out</h2>
                <p>
                    Your session will expire in <strong>1 minute</strong> due to inactivity.
                </p>
                <p>Tap the button below to continue your application.</p>
                <button
                    className="btn-kiosk-primary btn-pulse"
                    onClick={handleContinue}
                >
                    ✋ I'm Still Here
                </button>
            </div>
        </div>
    );
}
