import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import AgriSlideshow from '../components/AgriSlideshow';

export default function EmployeeLandingPage() {
    const navigate = useNavigate();
    const [showHelpVideo, setShowHelpVideo] = useState(false);

    return (
        <>
            <AgriSlideshow />
            <div className="landing-page">
                {/* Top pill */}
                <div className="landing-pill">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ color: 'var(--green-mid)' }}>
                        <path d="M12 2L15 8L22 9L17 14L18 21L12 18L6 21L7 14L2 9L9 8Z" />
                    </svg>
                    Secure Loan Management System
                </div>

                {/* Hero card */}
                <div className="landing-hero-card">
                    <div className="landing-icon-wrap animate-1">
                        <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" style={{ color: 'var(--green-mid)' }}>
                            <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2z" />
                            <path d="M12 6v6l4 2" />
                            <path d="M7 10.5c1-2 3-3.5 5-3.5s4 1.5 5 3.5" />
                            <path d="M9 15c.5 1.5 1.5 2.5 3 2.5s2.5-1 3-2.5" />
                        </svg>
                    </div>

                    <h1 className="landing-heading animate-2">
                        Rural Credit Management
                    </h1>

                    <p className="landing-subheading animate-3">
                        Empowering farmers with transparent, secure,
                        and dignified access to credit
                    </p>

                    <div className="landing-divider" />

                    <button
                        className="btn-primary pulse landing-btn animate-4"
                        onClick={() => navigate('/login')}
                    >
                        Begin Session →
                    </button>
                </div>

                {/* Trust indicators */}
                <div className="landing-trust-row">
                    <span className="badge badge-green">🔒 Ed25519 Secured</span>
                    <span className="badge badge-green">⛓ Blockchain Anchored</span>
                    <span className="badge badge-green">🌾 Farmer First</span>
                </div>
            </div>

            {/* Floating Help Video Button */}
            <button
                onClick={() => setShowHelpVideo(true)}
                style={{
                    position: 'fixed',
                    bottom: '28px',
                    right: '28px',
                    zIndex: 9000,
                    background: 'linear-gradient(135deg, #1565c0, #1e88e5)',
                    color: '#fff',
                    border: 'none',
                    borderRadius: '50px',
                    padding: '14px 24px',
                    fontSize: '1rem',
                    fontWeight: 600,
                    cursor: 'pointer',
                    boxShadow: '0 4px 20px rgba(21,101,192,0.4)',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px',
                    transition: 'transform 0.2s',
                }}
                onMouseEnter={e => e.currentTarget.style.transform = 'scale(1.05)'}
                onMouseLeave={e => e.currentTarget.style.transform = 'scale(1)'}
                title="Watch help video"
            >
                <span style={{ fontSize: '1.3rem' }}>🎬</span>
                Help Demo
            </button>

            {/* Help Video Modal */}
            {showHelpVideo && (
                <div
                    style={{
                        position: 'fixed',
                        top: 0,
                        left: 0,
                        right: 0,
                        bottom: 0,
                        zIndex: 10000,
                        background: 'rgba(0,0,0,0.8)',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                    }}
                    onClick={() => setShowHelpVideo(false)}
                >
                    <div
                        style={{
                            background: '#111',
                            borderRadius: '16px',
                            padding: '12px',
                            maxWidth: '90vw',
                            maxHeight: '90vh',
                            position: 'relative',
                        }}
                        onClick={e => e.stopPropagation()}
                    >
                        <button
                            onClick={() => setShowHelpVideo(false)}
                            style={{
                                position: 'absolute',
                                top: '-12px',
                                right: '-12px',
                                background: '#e53935',
                                color: '#fff',
                                border: 'none',
                                borderRadius: '50%',
                                width: '36px',
                                height: '36px',
                                fontSize: '1.2rem',
                                fontWeight: 700,
                                cursor: 'pointer',
                                zIndex: 10001,
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                                boxShadow: '0 2px 10px rgba(0,0,0,0.3)',
                            }}
                        >
                            ✕
                        </button>
                        <video
                            src="/EMPLOYEE_SIDE_DEMO_HELP.mp4"
                            controls
                            autoPlay
                            style={{
                                maxWidth: '85vw',
                                maxHeight: '80vh',
                                borderRadius: '12px',
                                display: 'block',
                            }}
                        />
                    </div>
                </div>
            )}
        </>
    );
}
