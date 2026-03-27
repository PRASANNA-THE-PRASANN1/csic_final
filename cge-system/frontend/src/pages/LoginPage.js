import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth, ROLE_LANDING, ROLE_LABELS } from '../AuthContext';
import AgriSlideshow from '../components/AgriSlideshow';

export default function LoginPage() {
    const [userId, setUserId] = useState('');
    const [password, setPassword] = useState('');
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');
    const { login } = useAuth();
    const navigate = useNavigate();

    const handleSubmit = async (e) => {
        e.preventDefault();
        if (!userId.trim() || !password.trim()) {
            setError('Please enter both User ID and Password');
            return;
        }
        setLoading(true);
        setError('');
        try {
            const userData = await login(userId.trim(), password);
            navigate(ROLE_LANDING[userData.role] || '/');
        } catch (err) {
            setError(err.response?.data?.detail || 'Invalid credentials. Please try again.');
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="login-page">
            {/* Left panel — slideshow */}
            <div className="login-slideshow-panel">
                <AgriSlideshow />
                <div className="slideshow-overlay" />
            </div>

            {/* Right panel — login form */}
            <div className="login-card">
                <div className="login-header">
                    <span className="login-logo">🌾</span>
                    <h1 className="login-title">Officer Login</h1>
                    <p className="login-subtitle">Secure access to loan management</p>
                </div>

                <form onSubmit={handleSubmit} className="login-form">
                    <div className="login-field">
                        <label htmlFor="userId">User ID</label>
                        <input
                            id="userId"
                            type="text"
                            value={userId}
                            onChange={(e) => setUserId(e.target.value)}
                            placeholder="e.g. EMP101, CLERK001"
                            autoFocus
                            autoComplete="username"
                        />
                    </div>

                    <div className="login-field">
                        <label htmlFor="password">Password</label>
                        <input
                            id="password"
                            type="password"
                            value={password}
                            onChange={(e) => setPassword(e.target.value)}
                            placeholder="Enter your password"
                            autoComplete="current-password"
                        />
                    </div>

                    {error && <div className="login-error">{error}</div>}

                    <button type="submit" className="login-btn" disabled={loading}>
                        {loading ? (
                            <><span className="login-spinner" /> Authenticating...</>
                        ) : (
                            'Sign In →'
                        )}
                    </button>
                </form>

                <p style={{ textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.75rem', marginTop: 'var(--space-md)' }}>
                    🔒 JWT secured session · bcrypt authentication
                </p>

                <div className="login-credentials">
                    <h4>Demo Credentials</h4>
                    <div className="credentials-grid">
                        {[
                            { id: 'CLERK001', pw: 'clerk123', role: 'clerk' },
                            { id: 'EMP101', pw: 'mgr123', role: 'branch_manager' },
                            { id: 'EMP201', pw: 'mgr123', role: 'regional_manager' },
                            { id: 'EMP301', pw: 'mgr123', role: 'credit_head' },
                            { id: 'EMP401', pw: 'mgr123', role: 'zonal_head' },
                            { id: 'AUD001', pw: 'audit123', role: 'auditor' },
                        ].map((c) => (
                            <button
                                key={c.id}
                                type="button"
                                className="credential-chip"
                                onClick={() => { setUserId(c.id); setPassword(c.pw); setError(''); }}
                            >
                                <span className="chip-id">{c.id}</span>
                                <span className="chip-role">{ROLE_LABELS[c.role]}</span>
                            </button>
                        ))}
                    </div>
                </div>
            </div>
        </div>
    );
}
