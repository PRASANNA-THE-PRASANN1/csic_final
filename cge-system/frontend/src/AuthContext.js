/**
 * Authentication Context – provides user state, login, and logout.
 * Persists user to localStorage for session continuity.
 */

import React, { createContext, useContext, useState, useEffect } from 'react';
import { loginUser as apiLogin } from './api';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
    const [user, setUser] = useState(null);
    const [loading, setLoading] = useState(true);

    // Restoring session from localStorage on mount
    useEffect(() => {
        try {
            const stored = localStorage.getItem('cge_user');
            if (stored) {
                setUser(JSON.parse(stored));
            }
        } catch {
            localStorage.removeItem('cge_user');
        }
        setLoading(false);
    }, []);

    const login = async (userId, password) => {
        const res = await apiLogin(userId, password);
        const userData = {
            user_id: res.data.user_id,
            name: res.data.name,
            role: res.data.role,
            token: res.data.token,
        };
        setUser(userData);
        localStorage.setItem('cge_user', JSON.stringify(userData));
        return userData;
    };

    const logout = () => {
        setUser(null);
        localStorage.removeItem('cge_user');
    };

    return (
        <AuthContext.Provider value={{ user, login, logout, loading, isAuthenticated: !!user }}>
            {children}
        </AuthContext.Provider>
    );
}

export function useAuth() {
    const ctx = useContext(AuthContext);
    if (!ctx) throw new Error('useAuth must be used within AuthProvider');
    return ctx;
}

// Role landing page mapping
export const ROLE_LANDING = {
    clerk: '/clerk/review',
    branch_manager: '/approval',
    credit_manager: '/approval',
    ceo: '/approval',
    board_member: '/approval',
    auditor: '/audit',
};

// Role allowed nav items
export const ROLE_NAV = {
    clerk: [
        { path: '/clerk/review', label: '📋 Pending Review' },
    ],
    branch_manager: [
        { path: '/approval', label: '🏦 Approvals' },
        { path: '/audit', label: '🔍 Audit' },
    ],
    credit_manager: [
        { path: '/approval', label: '🏦 Approvals' },
        { path: '/audit', label: '🔍 Audit' },
    ],
    ceo: [
        { path: '/approval', label: '🏦 Approvals' },
        { path: '/audit', label: '🔍 Audit' },
        { path: '/dashboard', label: '📊 Dashboard' },
    ],
    board_member: [
        { path: '/approval', label: '🏦 Approvals' },
        { path: '/audit', label: '🔍 Audit' },
        { path: '/dashboard', label: '📊 Dashboard' },
    ],
    auditor: [
        { path: '/audit', label: '🔍 Audit' },
        { path: '/dashboard', label: '📊 Dashboard' },
    ],
};

// Friendly role labels
export const ROLE_LABELS = {
    clerk: 'Bank Clerk',
    branch_manager: 'Branch Manager',
    credit_manager: 'Credit Manager',
    ceo: 'CEO',
    board_member: 'Board Member',
    auditor: 'Auditor',
};
