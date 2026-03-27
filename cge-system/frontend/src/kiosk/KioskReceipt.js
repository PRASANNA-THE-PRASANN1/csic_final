/**
 * KioskReceipt — Success screen after loan application completion.
 */

import React from 'react';
import { useKiosk } from './KioskContext';

export default function KioskReceipt() {
    const { state, dispatch } = useKiosk();

    return (
        <div className="kiosk-step kiosk-receipt">
            <div className="kiosk-receipt-success">
                <div className="kiosk-receipt-icon">🎉</div>
                <h2>Application Submitted Successfully!</h2>
                <p className="kiosk-receipt-subtitle">
                    Your loan application has been received and anchored on the blockchain.
                </p>
            </div>

            <div className="kiosk-receipt-card">
                <div className="kiosk-receipt-details">
                    <div className="kiosk-receipt-row">
                        <span className="label">Loan ID</span>
                        <span className="value mono">{state.loanId}</span>
                    </div>
                    <div className="kiosk-receipt-row">
                        <span className="label">Applicant</span>
                        <span className="value">{state.farmerName}</span>
                    </div>
                    <div className="kiosk-receipt-row">
                        <span className="label">Amount</span>
                        <span className="value highlight">₹{Number(state.amount || 0).toLocaleString('en-IN')}</span>
                    </div>
                    <div className="kiosk-receipt-row">
                        <span className="label">Purpose</span>
                        <span className="value">{state.purpose}</span>
                    </div>
                    {state.anchorHash && (
                        <div className="kiosk-receipt-row">
                            <span className="label">Blockchain Anchor</span>
                            <span className="value mono small">
                                {state.anchorHash.substring(0, 16)}...
                            </span>
                        </div>
                    )}
                    {state.blockNumber && (
                        <div className="kiosk-receipt-row">
                            <span className="label">Block #</span>
                            <span className="value">{state.blockNumber}</span>
                        </div>
                    )}
                </div>
            </div>

            <div className="kiosk-receipt-next-steps">
                <h3>What happens next?</h3>
                <div className="kiosk-next-steps-list">
                    <div className="kiosk-next-step">
                        <span className="kiosk-next-step-num">1</span>
                        <span>A bank clerk will review your application</span>
                    </div>
                    <div className="kiosk-next-step">
                        <span className="kiosk-next-step-num">2</span>
                        <span>Manager approvals based on loan tier</span>
                    </div>
                    <div className="kiosk-next-step">
                        <span className="kiosk-next-step-num">3</span>
                        <span>CBS validation and loan execution</span>
                    </div>
                    <div className="kiosk-next-step">
                        <span className="kiosk-next-step-num">4</span>
                        <span>SMS notification when approved</span>
                    </div>
                </div>
            </div>

            <button
                className="btn-kiosk-primary"
                onClick={() => dispatch({ type: 'RESET' })}
            >
                🏠 Start New Application
            </button>
        </div>
    );
}
