import React from 'react';
import { useNavigate } from 'react-router-dom';

const roles = [
    {
        id: 'clerk',
        icon: '📋',
        title: 'Bank Clerk',
        subtitle: 'Loan Originator',
        description: 'Create new loan applications and enter borrower details.',
        path: '/loan/create',
        gradient: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
    },
    {
        id: 'farmer',
        icon: '🌾',
        title: 'Farmer',
        subtitle: 'Borrower',
        description: 'Review and cryptographically consent to loan terms.',
        path: '/loan/consent',
        gradient: 'linear-gradient(135deg, #f093fb 0%, #f5576c 100%)',
    },
    {
        id: 'manager',
        icon: '🏦',
        title: 'Bank Manager',
        subtitle: 'Approver',
        description: 'Review and approve loans according to policy tiers.',
        path: '/approval',
        gradient: 'linear-gradient(135deg, #4facfe 0%, #00f2fe 100%)',
    },
    {
        id: 'auditor',
        icon: '🔍',
        title: 'Auditor',
        subtitle: 'Verification Specialist',
        description: 'Verify loan integrity and detect tampering.',
        path: '/audit',
        gradient: 'linear-gradient(135deg, #43e97b 0%, #38f9d7 100%)',
    },
];

export default function HomePage() {
    const navigate = useNavigate();

    return (
        <div className="home-page">
            <div className="hero-section">
                <h1 className="hero-title">
                    <span className="hero-icon">🔐</span>
                    Cryptographic Governance Engine
                </h1>
                <p className="hero-subtitle">
                    Fraud-proof loan processing with cryptographic signing, multi-level approvals,
                    and blockchain-anchored audit trail.
                </p>
            </div>

            <div className="role-grid">
                {roles.map((role) => (
                    <div
                        key={role.id}
                        className="role-card"
                        style={{ '--card-gradient': role.gradient }}
                        onClick={() => navigate(role.path)}
                    >
                        <div className="role-card-icon">{role.icon}</div>
                        <h2 className="role-card-title">{role.title}</h2>
                        <span className="role-card-subtitle">{role.subtitle}</span>
                        <p className="role-card-desc">{role.description}</p>
                        <div className="role-card-arrow">→</div>
                    </div>
                ))}
            </div>

            <div className="home-footer">
                <p>CGE System v1.0 &middot; Powered by SHA-256 &amp; Ed25519 Cryptography</p>
            </div>
        </div>
    );
}
