/**
 * KioskStart — Welcome screen with mandatory employee assistant registration.
 * An employee must be assigned before any kiosk session can begin.
 */

import React, { useState } from 'react';
import { useKiosk } from './KioskContext';
import { kioskStart } from '../api';

export default function KioskStart() {
    const { state, dispatch } = useKiosk();
    const [employeeName, setEmployeeName] = useState('');
    const [employeeId, setEmployeeId] = useState('');
    const [validationError, setValidationError] = useState('');

    const canStart = employeeName.trim().length > 0 && employeeId.trim().length > 0;

    const handleStart = async () => {
        if (!canStart) {
            setValidationError('Both Employee Name and Employee ID are required');
            return;
        }
        setValidationError('');
        dispatch({ type: 'SET_LOADING', value: true });
        dispatch({ type: 'SET_ERROR', error: null });
        try {
            const res = await kioskStart(employeeName.trim(), employeeId.trim());
            const data = res.data;
            dispatch({ type: 'SET_SESSION', token: data.session_token, loanId: data.loan_id });
            dispatch({ type: 'SET_EMPLOYEE', name: employeeName.trim(), id: employeeId.trim() });
            dispatch({ type: 'NEXT_STEP' });
        } catch (err) {
            const msg = err.response?.data?.detail;
            const errorMsg = typeof msg === 'object' ? msg.message || JSON.stringify(msg) : msg || 'Failed to start session';
            dispatch({ type: 'SET_ERROR', error: errorMsg });
        } finally {
            dispatch({ type: 'SET_LOADING', value: false });
        }
    };

    return (
        <div className="kiosk-step kiosk-start">
            <div className="kiosk-start-hero">
                <div className="kiosk-start-icon">🏧</div>
                <h2>Welcome to the Loan Application Kiosk</h2>
                <p className="kiosk-hindi">ऋण आवेदन कियोस्क में आपका स्वागत है</p>
                <p className="kiosk-start-desc">
                    This kiosk will guide the farmer through the loan application process.
                    An assigned bank employee must be present to assist throughout.
                </p>

                {/* Mandatory Employee Assignment */}
                <div className="kiosk-employee-mandatory">
                    <div className="kiosk-employee-mandatory-header">
                        <span className="kiosk-employee-mandatory-icon">👨‍💼</span>
                        <h3>Assigned Employee / सौंपा गया कर्मचारी</h3>
                    </div>
                    <p className="kiosk-employee-mandatory-note">
                        ⚠️ A bank employee <strong>must</strong> be assigned to assist the farmer
                        throughout the entire application process. This is mandatory.
                    </p>
                    <div className="kiosk-employee-fields">
                        <div className="kiosk-form-group">
                            <label>Employee Name / कर्मचारी का नाम <span className="required">*</span></label>
                            <input
                                type="text"
                                className="kiosk-input"
                                value={employeeName}
                                onChange={(e) => { setEmployeeName(e.target.value); setValidationError(''); }}
                                placeholder="e.g. Anil Kumar"
                                autoFocus
                            />
                        </div>
                        <div className="kiosk-form-group">
                            <label>Employee ID / कर्मचारी आईडी <span className="required">*</span></label>
                            <input
                                type="text"
                                className="kiosk-input"
                                value={employeeId}
                                onChange={(e) => { setEmployeeId(e.target.value); setValidationError(''); }}
                                placeholder="e.g. CLERK001"
                            />
                        </div>
                        {validationError && (
                            <div className="kiosk-field-error">⚠️ {validationError}</div>
                        )}
                        <div className="kiosk-employee-note">
                            ℹ️ Employee details are recorded immutably and will be bound to this loan application
                            from start to finish. They cannot be modified later.
                        </div>
                    </div>
                </div>

                <div className="kiosk-start-steps">
                    <div className="kiosk-info-card">
                        <span className="kiosk-info-icon">📋</span>
                        <span>Review terms & conditions</span>
                    </div>
                    <div className="kiosk-info-card">
                        <span className="kiosk-info-icon">🪪</span>
                        <span>Verify identity with Aadhaar</span>
                    </div>
                    <div className="kiosk-info-card">
                        <span className="kiosk-info-icon">📄</span>
                        <span>Upload loan documents</span>
                    </div>
                    <div className="kiosk-info-card">
                        <span className="kiosk-info-icon">✅</span>
                        <span>Confirm and give consent</span>
                    </div>
                </div>
                <button
                    className="btn-kiosk-primary btn-large"
                    onClick={handleStart}
                    disabled={state.loading || !canStart}
                    title={!canStart ? 'Please fill in both Employee Name and Employee ID' : ''}
                >
                    {state.loading ? '⏳ Starting Session...' : '🚀 Start Application / आवेदन शुरू करें'}
                </button>
                {!canStart && (
                    <p className="kiosk-start-hint">
                        👆 Enter employee details above to enable the start button
                    </p>
                )}
            </div>
        </div>
    );
}
