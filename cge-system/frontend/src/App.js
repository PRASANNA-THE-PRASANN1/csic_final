import React from 'react';
import { BrowserRouter as Router, Routes, Route, Link, Navigate, useLocation } from 'react-router-dom';
import { AuthProvider, useAuth, ROLE_NAV, ROLE_LABELS, ROLE_LANDING } from './AuthContext';
import LoginPage from './pages/LoginPage';
import EmployeeLandingPage from './pages/EmployeeLandingPage';
import LoanCreatePage from './pages/LoanCreatePage';
import ApprovalPage from './pages/ApprovalPage';
import AuditPage from './pages/AuditPage';
import RegulatoryDashboard from './pages/RegulatoryDashboard';
import ClerkReviewPage from './pages/ClerkReviewPage';
import KioskApp from './kiosk/KioskApp';
import KioskLandingPage from './kiosk/KioskLandingPage';
import './index.css';

function ProtectedRoute({ children, allowedRoles }) {
    const { user, isAuthenticated, loading } = useAuth();
    if (loading) return null;
    if (!isAuthenticated) return <Navigate to="/login" replace />;
    if (allowedRoles && !allowedRoles.includes(user.role)) {
        return <Navigate to={ROLE_LANDING[user.role] || '/login'} replace />;
    }
    return children;
}

function AppNavbar() {
    const { user, logout, isAuthenticated } = useAuth();
    const location = useLocation();
    if (!isAuthenticated) return null;
    // Hide navbar on kiosk routes
    if (location.pathname.startsWith('/kiosk')) return null;

    const navItems = ROLE_NAV[user.role] || [];

    return (
        <nav className="navbar">
            <span className="navbar-brand">
                <span className="brand-icon">🔐</span> CGE System
            </span>

            <ul className="navbar-links">
                {navItems.map((item) => (
                    <li key={item.path}>
                        <Link
                            to={item.path}
                            className={location.pathname === item.path ? 'active' : ''}
                        >
                            {item.label}
                        </Link>
                    </li>
                ))}
            </ul>

            <div className="navbar-user">
                <div className="user-badge">
                    <span className="user-avatar">
                        {user.name.charAt(0).toUpperCase()}
                    </span>
                    <div className="user-info">
                        <span className="user-name">{user.name}</span>
                        <span className="user-role">{ROLE_LABELS[user.role]}</span>
                    </div>
                </div>
                <button className="btn-logout" onClick={logout}>
                    ⏻ Logout
                </button>
            </div>
        </nav>
    );
}

function AppRoutes() {
    const { isAuthenticated, user, loading } = useAuth();

    if (loading) return null;

    return (
        <Routes>
            <Route
                path="/login"
                element={
                    isAuthenticated
                        ? <Navigate to={ROLE_LANDING[user.role] || '/'} replace />
                        : <LoginPage />
                }
            />

            {/* Public kiosk routes */}
            <Route path="/kiosk" element={<KioskLandingPage />} />
            <Route path="/kiosk/start" element={<KioskApp />} />
            <Route path="/kiosk/:loanId" element={<KioskApp />} />

            <Route
                path="/clerk/review"
                element={
                    <ProtectedRoute allowedRoles={['clerk']}>
                        <ClerkReviewPage />
                    </ProtectedRoute>
                }
            />

            <Route
                path="/loan/create"
                element={
                    <ProtectedRoute allowedRoles={['clerk']}>
                        <LoanCreatePage />
                    </ProtectedRoute>
                }
            />

            <Route
                path="/approval"
                element={
                    <ProtectedRoute allowedRoles={['clerk', 'branch_manager', 'credit_manager', 'ceo', 'board_member']}>
                        <ApprovalPage />
                    </ProtectedRoute>
                }
            />

            <Route
                path="/audit"
                element={
                    <ProtectedRoute allowedRoles={['branch_manager', 'credit_manager', 'ceo', 'board_member', 'auditor']}>
                        <AuditPage />
                    </ProtectedRoute>
                }
            />

            <Route
                path="/dashboard"
                element={
                    <ProtectedRoute allowedRoles={['auditor', 'ceo', 'board_member']}>
                        <RegulatoryDashboard />
                    </ProtectedRoute>
                }
            />

            {/* Employee landing page */}
            <Route
                path="/"
                element={
                    isAuthenticated
                        ? <Navigate to={ROLE_LANDING[user.role] || '/login'} replace />
                        : <EmployeeLandingPage />
                }
            />

            {/* Default: go to landing or role landing */}
            <Route
                path="*"
                element={
                    isAuthenticated
                        ? <Navigate to={ROLE_LANDING[user.role] || '/login'} replace />
                        : <Navigate to="/" replace />
                }
            />
        </Routes>
    );
}

export default function App() {
    return (
        <Router>
            <AuthProvider>
                <div className="app-container">
                    <AppNavbar />
                    <main className="page">
                        <AppRoutes />
                    </main>
                </div>
            </AuthProvider>
        </Router>
    );
}

