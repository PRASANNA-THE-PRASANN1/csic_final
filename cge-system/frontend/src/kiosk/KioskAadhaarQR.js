/**
 * KioskAadhaarQR — Step 3: Aadhaar QR Code Scan (MOCK)
 * Currently simulates a QR scan with pre-set farmer data.
 * Will be replaced with real html5-qrcode scanner implementation later.
 */

import React, { useState, useCallback } from 'react';
import { useKiosk } from './KioskContext';
import { kioskAadhaarQRScan } from '../api';

// Mock Aadhaar data for demo
const MOCK_AADHAAR_DATA = {
    name: 'Ramesh Kumar Sharma',
    dob: '15-06-1985',
    gender: 'M',
    address: 'Village Sundarpur, Block Phulera, Dist. Jaipur, Rajasthan 303338',
    aadhaar_last_four: '7842',
};

export default function KioskAadhaarQR() {
    const { state, dispatch } = useKiosk();
    const [scanned, setScanned] = useState(false);
    const [submitting, setSubmitting] = useState(false);
    const [error, setError] = useState(null);

    const handleMockScan = useCallback(() => {
        setScanned(true);
        setError(null);
    }, []);

    const handleSubmit = useCallback(async () => {
        setSubmitting(true);
        setError(null);

        try {
            const result = await kioskAadhaarQRScan(state.loanId, {
                name: MOCK_AADHAAR_DATA.name,
                dob: MOCK_AADHAAR_DATA.dob,
                gender: MOCK_AADHAAR_DATA.gender,
                address: MOCK_AADHAAR_DATA.address,
                aadhaar_last_four: MOCK_AADHAAR_DATA.aadhaar_last_four,
                photo_base64: '',  // No photo for mock
            }, state.sessionToken);

            dispatch({
                type: 'SET_AADHAAR_QR',
                data: {
                    name: result.data.verified_name || MOCK_AADHAAR_DATA.name,
                    dob: MOCK_AADHAAR_DATA.dob,
                    gender: MOCK_AADHAAR_DATA.gender,
                    address: MOCK_AADHAAR_DATA.address,
                    aadhaar_last_four: result.data.aadhaar_last_four || MOCK_AADHAAR_DATA.aadhaar_last_four,
                    photo_base64: '',
                },
            });

            dispatch({ type: 'NEXT_STEP' });
        } catch (e) {
            const msg = e.response?.data?.detail || e.message || 'Failed to process QR data';
            setError(typeof msg === 'object' ? msg.message : msg);
        } finally {
            setSubmitting(false);
        }
    }, [state.loanId, state.sessionToken, dispatch]);

    return (
        <div className="kiosk-step" id="kiosk-step-aadhaar-qr">
            <div className="kiosk-step-header">
                <div className="kiosk-step-icon">📱</div>
                <h2>Step 3: Aadhaar QR Scan</h2>
                <p>Scan the QR code on the farmer's Aadhaar card to extract identity details.</p>
            </div>

            {error && (
                <div className="kiosk-error" style={{ marginBottom: '1rem' }}>
                    <span>⚠️</span> {error}
                </div>
            )}

            {!scanned ? (
                <div style={{ textAlign: 'center' }}>
                    <div style={{
                        background: 'linear-gradient(135deg, #fef3c7, #fde68a)',
                        border: '2px dashed #f59e0b',
                        borderRadius: '16px',
                        padding: '2rem',
                        maxWidth: '400px',
                        margin: '0 auto 1.5rem',
                    }}>
                        <div style={{ fontSize: '4rem', marginBottom: '0.5rem' }}>📷</div>
                        <p style={{ color: '#92400e', fontWeight: '600', marginBottom: '0.5rem' }}>
                            QR Scanner (Demo Mode)
                        </p>
                        <p style={{ color: '#a16207', fontSize: '0.85rem' }}>
                            In production, this will open the camera and scan the Aadhaar QR code.
                        </p>
                    </div>
                    <button
                        className="btn-kiosk-primary"
                        onClick={handleMockScan}
                        style={{ fontSize: '1.1rem', padding: '1rem 2.5rem' }}
                    >
                        📱 Simulate QR Scan
                    </button>
                </div>
            ) : (
                <div style={{ maxWidth: '500px', margin: '0 auto' }}>
                    <div style={{
                        background: 'linear-gradient(135deg, #ecfdf5, #f0fdf4)',
                        border: '2px solid #10b981',
                        borderRadius: '12px',
                        padding: '1.5rem',
                        marginBottom: '1.5rem',
                    }}>
                        <h3 style={{ color: '#059669', marginBottom: '1rem' }}>
                            ✅ QR Code Scanned Successfully
                        </h3>
                        <div style={{ display: 'grid', gap: '0.75rem' }}>
                            <div><strong>Name:</strong> {MOCK_AADHAAR_DATA.name}</div>
                            <div><strong>Aadhaar:</strong> XXXX-XXXX-{MOCK_AADHAAR_DATA.aadhaar_last_four}</div>
                            <div><strong>DOB:</strong> {MOCK_AADHAAR_DATA.dob}</div>
                            <div><strong>Gender:</strong> {MOCK_AADHAAR_DATA.gender}</div>
                            <div><strong>Address:</strong> {MOCK_AADHAAR_DATA.address}</div>
                        </div>
                    </div>

                    <div style={{ display: 'flex', gap: '0.5rem' }}>
                        <button
                            className="btn-kiosk-secondary"
                            onClick={() => setScanned(false)}
                        >
                            ↺ Rescan
                        </button>
                        <button
                            className="btn-kiosk-primary"
                            onClick={handleSubmit}
                            disabled={submitting}
                            style={{ flex: 1 }}
                        >
                            {submitting ? 'Processing...' : 'Confirm & Continue →'}
                        </button>
                    </div>
                </div>
            )}
        </div>
    );
}
