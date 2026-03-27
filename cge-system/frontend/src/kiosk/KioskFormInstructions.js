/**
 * KioskFormInstructions — Step 5: Instructional screen.
 * Tells the farmer to collect and fill the physical loan form before scanning.
 */

import React, { useState } from 'react';
import { useKiosk } from './KioskContext';

export default function KioskFormInstructions() {
    const { dispatch } = useKiosk();
    const [ready, setReady] = useState(false);

    return (
        <div className="kiosk-step kiosk-form-instructions">
            <h2 className="kiosk-step-title">📝 Fill Your Loan Application Form</h2>
            <p className="kiosk-step-subtitle">
                कृपया बैंक काउंटर से ऋण आवेदन पत्र लें और भरें
            </p>

            <div className="kiosk-instructions-card">
                <div className="kiosk-instruction-list">
                    <div className="kiosk-instruction-item">
                        <span className="kiosk-instruction-number">1</span>
                        <div>
                            <strong>Collect the form / फॉर्म लें</strong>
                            <p>Ask the bank employee for a loan application form.</p>
                        </div>
                    </div>
                    <div className="kiosk-instruction-item">
                        <span className="kiosk-instruction-number">2</span>
                        <div>
                            <strong>Fill in your details / विवरण भरें</strong>
                            <p>Write your <strong>Loan ID</strong>, desired <strong>amount</strong>, <strong>purpose</strong>, and personal details clearly.</p>
                        </div>
                    </div>
                    <div className="kiosk-instruction-item">
                        <span className="kiosk-instruction-number">3</span>
                        <div>
                            <strong>Sign the form / फॉर्म पर हस्ताक्षर करें</strong>
                            <p>Sign at the bottom of the form. Your signature will be verified.</p>
                        </div>
                    </div>
                    <div className="kiosk-instruction-item">
                        <span className="kiosk-instruction-number">4</span>
                        <div>
                            <strong>Scan or photo / स्कैन या फोटो लें</strong>
                            <p>In the next step, you will upload a photo or scan of the completed form.</p>
                        </div>
                    </div>
                </div>

                <div className="kiosk-instruction-tip">
                    💡 <strong>Tip:</strong> Write clearly in block letters. The system will read your handwriting automatically.
                </div>
            </div>

            <div className="kiosk-form-ready">
                <label className="kiosk-checkbox-label">
                    <input
                        type="checkbox"
                        checked={ready}
                        onChange={(e) => setReady(e.target.checked)}
                    />
                    <span>I have completed and signed my loan application form / मैंने अपना आवेदन पत्र भर दिया है</span>
                </label>
            </div>

            <button
                className="btn-kiosk-primary"
                onClick={() => dispatch({ type: 'NEXT_STEP' })}
                disabled={!ready}
            >
                📄 Continue to Document Upload
            </button>
        </div>
    );
}
