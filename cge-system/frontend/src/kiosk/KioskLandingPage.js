import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import AgriSlideshow from '../components/AgriSlideshow';

function getGreeting() {
    const hour = new Date().getHours();
    if (hour < 12) return { hi: 'शुभ प्रभात 🌅', en: 'Good Morning' };
    if (hour < 17) return { hi: 'नमस्ते 🙏', en: 'Hello' };
    return { hi: 'शुभ संध्या 🌆', en: 'Good Evening' };
}

export default function KioskLandingPage() {
    const navigate = useNavigate();
    const [greeting, setGreeting] = useState(getGreeting());
    const [language, setLanguage] = useState('hi');
    const [showHelpVideo, setShowHelpVideo] = useState(false);

    useEffect(() => {
        const interval = setInterval(() => setGreeting(getGreeting()), 60000);
        return () => clearInterval(interval);
    }, []);

    const handleStart = () => {
        // Store language in sessionStorage so KioskContext can pick it up
        try { sessionStorage.setItem('kiosk_language', language); } catch(e) {}
        navigate('/kiosk/start');
    };

    return (
        <>
            <AgriSlideshow />
            <div className="landing-page">
                {/* Greeting pill */}
                <div className="landing-pill">
                    {greeting.hi} — {greeting.en}
                </div>

                {/* Hero card */}
                <div className="landing-hero-card wide">
                    <div className="landing-icon-wrap animate-1">
                        <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" style={{ color: 'var(--green-mid)' }}>
                            <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2z" />
                            <path d="M12 6v6l4 2" />
                            <path d="M7 10.5c1-2 3-3.5 5-3.5s4 1.5 5 3.5" />
                            <path d="M9 15c.5 1.5 1.5 2.5 3 2.5s2.5-1 3-2.5" />
                        </svg>
                    </div>

                    <h1 className="landing-heading large animate-2">
                        किसान ऋण सेवा
                    </h1>
                    <p className="landing-hindi animate-2" style={{ marginBottom: 'var(--space-sm)' }}>
                        Farmer Loan Service
                    </p>

                    <p className="landing-subheading animate-3" style={{ maxWidth: 440 }}>
                        आपका ऋण आवेदन सुरक्षित और पारदर्शी तरीके से शुरू करने के लिए नीचे दबाएं
                    </p>
                    <p className="landing-subheading animate-3" style={{ fontSize: '0.85rem', marginTop: '-8px' }}>
                        Press below to begin your loan application securely
                    </p>

                    <div className="landing-divider" />

                    <button
                        className="btn-primary pulse landing-btn large animate-4"
                        onClick={handleStart}
                    >
                        आवेदन शुरू करें / Start Application
                    </button>
                </div>

                {/* Info pills */}
                <div className="landing-trust-row">
                    <span className="badge badge-gold animate-3">📋 Aadhaar Required</span>
                    <span className="badge badge-gold animate-4">📄 Loan Form Required</span>
                    <span className="badge badge-gold animate-5">📞 Mobile Number Required</span>
                </div>

                {/* Language selector */}
                <div className="landing-lang-row">
                    <button
                        className={`lang-pill ${language === 'en' ? 'active' : ''}`}
                        onClick={() => setLanguage('en')}
                    >
                        English
                    </button>
                    <button
                        className={`lang-pill ${language === 'hi' ? 'active' : ''}`}
                        onClick={() => setLanguage('hi')}
                    >
                        हिंदी
                    </button>
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
                    background: 'linear-gradient(135deg, #2e7d32, #43a047)',
                    color: '#fff',
                    border: 'none',
                    borderRadius: '50px',
                    padding: '14px 24px',
                    fontSize: '1rem',
                    fontWeight: 600,
                    cursor: 'pointer',
                    boxShadow: '0 4px 20px rgba(46,125,50,0.4)',
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
                            src="/KIOSK_HELP_DEMO.mp4"
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
