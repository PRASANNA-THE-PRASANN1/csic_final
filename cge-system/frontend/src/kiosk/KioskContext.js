/**
 * KioskContext — State management for the sessionless kiosk flow.
 * Manages session token, loan ID, step progression, timeout, and assistance state.
 */

import React, { createContext, useContext, useReducer, useCallback, useEffect, useRef } from 'react';

const KioskContext = createContext(null);

const STEPS = [
    'start',        // 0 - Start/Welcome
    'terms',        // 1 - Terms & Conditions
    'aadhaarQR',    // 2 - Aadhaar QR Scan → Data Extraction (NEW)
    'presence',     // 3 - GPS + Photo capture + employee declaration
    'faceMatch',    // 4 - Face Match: Aadhaar photo vs live capture (NEW)
    'aadhaar',      // 5 - Aadhaar OTP verification
    'formReady',    // 6 - Form filling instructions
    'docUpload',    // 7 - Document upload
    'ocrConfirm',   // 8 - OCR results confirmation
    'consent',      // 9 - Final consent + IVR
    'receipt',      // 10 - Receipt with QR
];

const TIMEOUT_MS = 10 * 60 * 1000; // 10 minutes of inactivity
const WARNING_MS = 60 * 1000;      // Show warning 1 minute before timeout

const initialState = {
    step: 0,
    language: 'hi',
    sessionToken: null,
    loanId: null,
    farmerName: null,
    amount: null,
    purpose: null,
    aadhaarVerified: false,
    documentUploaded: false,
    ocrData: null,
    ocrConfirmed: false,
    consentCompleted: false,
    anchorHash: null,
    blockNumber: null,
    assistanceRequested: false,
    showTimeout: false,
    expired: false,
    error: null,
    loading: false,
    photoHash: null,
    livenessSuspicious: false,
    livenessVerified: false,
    livenessChallenges: null,
    employeeName: null,
    employeeId: null,
    aadhaar_qr_data: null,      // Extracted Aadhaar QR data (name, dob, gender, address, aadhaar_last_four, photo)
    face_match_result: null,    // Face match result (match_score, matched)
};

function reducer(state, action) {
    switch (action.type) {
        case 'SET_SESSION':
            return { ...state, sessionToken: action.token, loanId: action.loanId };
        case 'NEXT_STEP':
            return { ...state, step: Math.min(state.step + 1, STEPS.length - 1), error: null };
        case 'GO_TO_STEP':
            return { ...state, step: action.step, error: null };
        case 'SET_FARMER':
            return { ...state, farmerName: action.name, aadhaarVerified: true };
        case 'SET_LOAN_DATA':
            return { ...state, amount: action.amount, purpose: action.purpose };
        case 'SET_DOC_UPLOADED':
            return { ...state, documentUploaded: true };
        case 'SET_OCR_DATA':
            return { ...state, ocrData: action.data };
        case 'SET_OCR_CONFIRMED':
            return { ...state, ocrConfirmed: true };
        case 'SET_CONSENT_COMPLETE':
            return { ...state, consentCompleted: true };
        case 'SET_ANCHOR':
            return { ...state, anchorHash: action.hash, blockNumber: action.blockNumber };
        case 'SET_ASSISTANCE':
            return { ...state, assistanceRequested: action.value };
        case 'SET_PRESENCE_DATA':
            return {
                ...state,
                photoHash: action.photoHash,
                livenessSuspicious: action.livenessSuspicious,
                livenessVerified: action.activeLiveness || false,
            };
        case 'SET_LIVENESS_DATA':
            return { ...state, livenessChallenges: action.challenges, livenessVerified: action.verified };
        case 'SET_EMPLOYEE':
            return { ...state, employeeName: action.name, employeeId: action.id };
        case 'SET_AADHAAR_QR':
            return { ...state, aadhaar_qr_data: action.data };
        case 'SET_FACE_MATCH':
            return { ...state, face_match_result: action.data };
        case 'SHOW_TIMEOUT':
            return { ...state, showTimeout: true };
        case 'HIDE_TIMEOUT':
            return { ...state, showTimeout: false };
        case 'SET_EXPIRED':
            return { ...state, expired: true, showTimeout: false };
        case 'SET_ERROR':
            return { ...state, error: action.error, loading: false };
        case 'SET_LOADING':
            return { ...state, loading: action.value };
        case 'SET_LANGUAGE':
            return { ...state, language: action.language };
        case 'RESET':
            return { ...initialState };
        default:
            return state;
    }
}

export function KioskProvider({ children }) {
    const [state, dispatch] = useReducer(reducer, initialState);
    const timeoutRef = useRef(null);
    const warningRef = useRef(null);

    const resetTimers = useCallback(() => {
        if (timeoutRef.current) clearTimeout(timeoutRef.current);
        if (warningRef.current) clearTimeout(warningRef.current);
        if (!state.sessionToken || state.expired) return;

        dispatch({ type: 'HIDE_TIMEOUT' });

        warningRef.current = setTimeout(() => {
            dispatch({ type: 'SHOW_TIMEOUT' });
        }, TIMEOUT_MS - WARNING_MS);

        timeoutRef.current = setTimeout(() => {
            dispatch({ type: 'SET_EXPIRED' });
        }, TIMEOUT_MS);
    }, [state.sessionToken, state.expired]);

    // Reset timers on any user activity
    const onActivity = useCallback(() => {
        if (state.sessionToken && !state.expired) {
            resetTimers();
        }
    }, [state.sessionToken, state.expired, resetTimers]);

    // Set up activity listeners
    useEffect(() => {
        if (!state.sessionToken) return;
        const events = ['click', 'keydown', 'touchstart', 'scroll'];
        events.forEach(e => window.addEventListener(e, onActivity));
        resetTimers();
        return () => {
            events.forEach(e => window.removeEventListener(e, onActivity));
            if (timeoutRef.current) clearTimeout(timeoutRef.current);
            if (warningRef.current) clearTimeout(warningRef.current);
        };
    }, [state.sessionToken, onActivity, resetTimers]);

    const value = { state, dispatch, STEPS, onActivity };

    return (
        <KioskContext.Provider value={value}>
            {children}
        </KioskContext.Provider>
    );
}

export function useKiosk() {
    const ctx = useContext(KioskContext);
    if (!ctx) throw new Error('useKiosk must be within KioskProvider');
    return ctx;
}

export { STEPS };
