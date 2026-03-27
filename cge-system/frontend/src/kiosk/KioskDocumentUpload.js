/**
 * KioskDocumentUpload — Document upload step.
 * Accepts photo of the physical loan form, uploads to backend for hashing.
 */

import React, { useState, useRef } from 'react';
import { useKiosk } from './KioskContext';
import { kioskDocumentUpload, kioskDocumentOcr } from '../api';

export default function KioskDocumentUpload() {
    const { state, dispatch } = useKiosk();
    const [file, setFile] = useState(null);
    const [preview, setPreview] = useState(null);
    const [uploading, setUploading] = useState(false);
    const [uploaded, setUploaded] = useState(false);
    const [runningOcr, setRunningOcr] = useState(false);
    const fileRef = useRef(null);

    const handleFileSelect = (e) => {
        const selected = e.target.files[0];
        if (!selected) return;
        if (selected.size > 10 * 1024 * 1024) {
            dispatch({ type: 'SET_ERROR', error: 'File too large (max 10MB)' });
            return;
        }
        setFile(selected);
        const reader = new FileReader();
        reader.onload = (ev) => setPreview(ev.target.result);
        reader.readAsDataURL(selected);
    };

    const handleUpload = async () => {
        if (!file) return;
        setUploading(true);
        dispatch({ type: 'SET_ERROR', error: null });
        try {
            await kioskDocumentUpload(state.loanId, file, state.sessionToken);
            setUploaded(true);
            dispatch({ type: 'SET_DOC_UPLOADED' });
        } catch (err) {
            const msg = err.response?.data?.detail || 'Upload failed';
            dispatch({ type: 'SET_ERROR', error: typeof msg === 'object' ? msg.message : msg });
        } finally {
            setUploading(false);
        }
    };

    const handleRunOCR = async () => {
        setRunningOcr(true);
        dispatch({ type: 'SET_ERROR', error: null });
        try {
            const res = await kioskDocumentOcr(state.loanId, state.sessionToken);
            dispatch({ type: 'SET_OCR_DATA', data: res.data });
            dispatch({ type: 'NEXT_STEP' });
        } catch (err) {
            const msg = err.response?.data?.detail || 'OCR processing failed';
            dispatch({ type: 'SET_ERROR', error: typeof msg === 'object' ? msg.message : msg });
        } finally {
            setRunningOcr(false);
        }
    };

    return (
        <div className="kiosk-step kiosk-doc-upload">
            <h2 className="kiosk-step-title">📄 Document Upload</h2>
            <p className="kiosk-step-subtitle">
                Upload a photo of your signed loan application form.
            </p>

            <div className="kiosk-upload-area">
                {preview ? (
                    <div className="kiosk-preview-container">
                        <img src={preview} alt="Document preview" className="kiosk-doc-preview" />
                        {!uploaded && (
                            <button
                                className="btn-kiosk-secondary btn-small"
                                onClick={() => { setFile(null); setPreview(null); }}
                            >
                                ✕ Remove
                            </button>
                        )}
                    </div>
                ) : (
                    <div
                        className="kiosk-dropzone"
                        onClick={() => fileRef.current?.click()}
                    >
                        <span className="kiosk-dropzone-icon">📸</span>
                        <p>Tap to capture or select document photo</p>
                        <span className="kiosk-dropzone-hint">JPEG, PNG — max 10MB</span>
                    </div>
                )}
                <input
                    ref={fileRef}
                    type="file"
                    accept="image/*"
                    capture="environment"
                    onChange={handleFileSelect}
                    style={{ display: 'none' }}
                />
            </div>

            {file && !uploaded && (
                <button
                    className="btn-kiosk-primary"
                    onClick={handleUpload}
                    disabled={uploading}
                >
                    {uploading ? '⏳ Uploading & Hashing...' : '📤 Upload Document'}
                </button>
            )}

            {uploaded && (
                <div className="kiosk-upload-success">
                    <div className="kiosk-success-badge">✅ Document uploaded and hashed</div>
                    <button
                        className="btn-kiosk-primary"
                        onClick={handleRunOCR}
                        disabled={runningOcr}
                    >
                        {runningOcr ? '⏳ Running OCR...' : '🔍 Scan Document (OCR)'}
                    </button>
                </div>
            )}
        </div>
    );
}
