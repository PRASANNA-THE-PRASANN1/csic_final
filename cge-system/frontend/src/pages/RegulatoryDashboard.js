/**
 * RegulatoryDashboard.js — National Fraud Prevention Intelligence Dashboard (§3.2)
 * Access: auditor, board_member, ceo roles only.
 * Displays live statistics from GET /api/dashboard/stats with recharts bar charts.
 */

import React, { useState, useEffect } from 'react';
import { getDashboardStats } from '../api';
import {
    BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
    PieChart, Pie, Cell, Legend,
} from 'recharts';

const CHART_COLORS = ['#818cf8', '#4ae3c0', '#fbbf24', '#f87171', '#64d8ff', '#a78bfa'];

export default function RegulatoryDashboard() {
    const [stats, setStats] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');

    useEffect(() => {
        (async () => {
            try {
                const res = await getDashboardStats();
                setStats(res.data);
            } catch (e) {
                setError(e.response?.data?.detail || 'Failed to load dashboard');
            } finally {
                setLoading(false);
            }
        })();
    }, []);

    /* ── Styles ── */
    const s = {
        container: { maxWidth: 1000, margin: '0 auto', animation: 'drift-up 0.5s ease-out' },
        glass: {
            background: 'rgba(14,14,36,0.55)', backdropFilter: 'blur(20px)',
            border: '1px solid rgba(255,255,255,0.06)', borderRadius: 18, padding: '2rem',
        },
        title: {
            fontSize: '1.5rem', fontWeight: 600,
            background: 'linear-gradient(135deg, #64d8ff, #a78bfa)',
            WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent',
            marginBottom: '0.3rem', letterSpacing: '0.02em',
        },
        subtitle: { fontSize: '0.88rem', color: '#8b96a9', marginBottom: '1.5rem', fontWeight: 300 },
        grid: {
            display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
            gap: 14, marginBottom: 24,
        },
        card: (accent) => ({
            background: `rgba(${accent}, 0.06)`,
            border: `1px solid rgba(${accent}, 0.2)`,
            borderRadius: 14, padding: '1.2rem', textAlign: 'center',
            transition: 'all 0.3s',
        }),
        cardValue: { fontSize: '2rem', fontWeight: 700, color: '#e8edf5', marginBottom: 4 },
        cardLabel: { fontSize: '0.78rem', color: '#8b96a9', fontWeight: 500, textTransform: 'uppercase', letterSpacing: '0.06em' },
        section: {
            marginTop: 24, paddingTop: 20,
            borderTop: '1px solid rgba(255,255,255,0.06)',
        },
        sectionTitle: { fontSize: '1.1rem', fontWeight: 500, color: '#c4cdd8', marginBottom: 16 },
        chainBadge: (ok) => ({
            display: 'inline-flex', alignItems: 'center', gap: 8,
            padding: '10px 20px', borderRadius: 12,
            background: ok ? 'rgba(74,227,192,0.08)' : 'rgba(248,113,113,0.08)',
            border: `1px solid ${ok ? 'rgba(74,227,192,0.25)' : 'rgba(248,113,113,0.25)'}`,
            fontSize: '0.95rem', fontWeight: 500,
            color: ok ? '#6ee7b7' : '#fca5a5',
        }),
        error: {
            color: '#fca5a5', background: 'rgba(248,113,113,0.08)',
            border: '1px solid rgba(248,113,113,0.25)',
            padding: '12px 16px', borderRadius: 12, marginBottom: '1rem', fontSize: '0.88rem',
        },
        chartContainer: {
            background: 'rgba(6,6,16,0.4)', borderRadius: 14, padding: '1.2rem',
            border: '1px solid rgba(255,255,255,0.06)',
        },
        timestamp: { textAlign: 'right', color: '#5b6578', fontSize: '0.78rem', marginTop: 16 },
    };

    if (loading) {
        return (
            <div style={s.container}>
                <div style={s.glass}>
                    <h1 style={s.title}>📊 National Fraud Prevention Intelligence Dashboard</h1>
                    <p style={{ textAlign: 'center', color: '#8b96a9', padding: 40 }}>⏳ Loading dashboard data...</p>
                </div>
            </div>
        );
    }

    if (error) {
        return (
            <div style={s.container}>
                <div style={s.glass}>
                    <h1 style={s.title}>📊 National Fraud Prevention Intelligence Dashboard</h1>
                    <div style={s.error} role="alert">⚠ {error}</div>
                </div>
            </div>
        );
    }

    // Prepare chart data
    const statusData = stats.loans_by_status
        ? Object.entries(stats.loans_by_status).map(([name, value]) => ({
            name: name.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()),
            count: value,
        }))
        : [];

    const tierData = stats.tier_distribution
        ? Object.entries(stats.tier_distribution).map(([name, value]) => ({
            name: name.toUpperCase().replace('_', ' '),
            count: value,
        }))
        : [];

    const fraudData = stats.fraud_detection
        ? [
            { name: 'Benami (Type 1)', count: stats.fraud_detection.type_1_benami || 0 },
            { name: 'Amount Inflation (Type 2)', count: stats.fraud_detection.type_2_amount_inflation || 0 },
            { name: 'Forgery Prevention (Type 3)', count: stats.fraud_detection.type_3_forgery_prevention || 0 },
        ]
        : [];

    const chainOk = stats.blockchain_integrity?.chain_valid;

    return (
        <div style={s.container}>
            <div style={s.glass}>
                <h1 style={s.title}>📊 National Fraud Prevention Intelligence Dashboard</h1>
                <p style={s.subtitle}>Real-time regulatory oversight · Cooperative Bank Fraud Intelligence</p>

                {/* KPI Cards */}
                <div style={s.grid} role="region" aria-label="Key Performance Indicators">
                    <div style={s.card('129,140,248')}>
                        <div style={s.cardValue}>{stats.total_loans || 0}</div>
                        <div style={s.cardLabel}>Total Loans</div>
                    </div>
                    <div style={s.card('74,227,192')}>
                        <div style={s.cardValue}>{stats.fraud_detection?.total_fraud_alerts || 0}</div>
                        <div style={s.cardLabel}>Fraud Alerts</div>
                    </div>
                    <div style={s.card('248,113,113')}>
                        <div style={s.cardValue}>{stats.override_events || 0}</div>
                        <div style={s.cardLabel}>Override Events</div>
                    </div>
                    <div style={s.card('100,216,255')}>
                        <div style={s.cardValue}>
                            {stats.avg_lifecycle_hours != null ? `${stats.avg_lifecycle_hours}h` : 'N/A'}
                        </div>
                        <div style={s.cardLabel}>Avg Lifecycle</div>
                    </div>
                    <div style={s.card('248,113,113')}>
                        <div style={s.cardValue}>{stats.manager_rejections?.manager_rejected_today || 0}</div>
                        <div style={s.cardLabel}>Mgr Rejected Today</div>
                    </div>
                </div>

                {/* Blockchain Integrity */}
                <div style={s.section} role="region" aria-label="Blockchain Integrity Status">
                    <h3 style={s.sectionTitle}>⛓ Blockchain Chain Integrity</h3>
                    <div style={s.chainBadge(chainOk)} aria-live="polite">
                        <span style={{ fontSize: '1.3rem' }}>{chainOk ? '✓' : '✗'}</span>
                        <span>{chainOk ? '✓ Chain Valid' : '✗ Chain Compromised'}</span>
                        <span style={{ color: '#8b96a9', fontSize: '0.82rem', marginLeft: 8 }}>
                            {stats.blockchain_integrity?.total_blocks || 0} blocks
                        </span>
                    </div>
                </div>

                {/* Charts Row */}
                <div style={{ ...s.section, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
                    {/* Loans by Status */}
                    <div style={s.chartContainer}>
                        <h3 style={{ ...s.sectionTitle, marginBottom: 12, fontSize: '0.95rem' }}>
                            📋 Loans by Status
                        </h3>
                        <ResponsiveContainer width="100%" height={250}>
                            <BarChart data={statusData}>
                                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                                <XAxis dataKey="name" tick={{ fill: '#8b96a9', fontSize: 10 }} angle={-25} textAnchor="end" height={60} />
                                <YAxis tick={{ fill: '#8b96a9', fontSize: 11 }} />
                                <Tooltip
                                    contentStyle={{ background: '#0e0e24', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8, color: '#e8edf5' }}
                                    labelStyle={{ color: '#64d8ff' }}
                                />
                                <Bar dataKey="count" fill="#818cf8" radius={[6, 6, 0, 0]} />
                            </BarChart>
                        </ResponsiveContainer>
                    </div>

                    {/* Tier Distribution */}
                    <div style={s.chartContainer}>
                        <h3 style={{ ...s.sectionTitle, marginBottom: 12, fontSize: '0.95rem' }}>
                            📊 Approval Tier Distribution
                        </h3>
                        <ResponsiveContainer width="100%" height={250}>
                            <PieChart>
                                <Pie
                                    data={tierData} dataKey="count" nameKey="name"
                                    cx="50%" cy="50%" outerRadius={80} label
                                >
                                    {tierData.map((_, idx) => (
                                        <Cell key={idx} fill={CHART_COLORS[idx % CHART_COLORS.length]} />
                                    ))}
                                </Pie>
                                <Tooltip
                                    contentStyle={{ background: '#0e0e24', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8, color: '#e8edf5' }}
                                />
                                <Legend wrapperStyle={{ color: '#8b96a9', fontSize: 11 }} />
                            </PieChart>
                        </ResponsiveContainer>
                    </div>
                </div>

                {/* Fraud Detection */}
                <div style={s.section} role="region" aria-label="Fraud Detection Statistics">
                    <h3 style={s.sectionTitle}>🚨 Fraud Detection by Type</h3>
                    <div style={s.chartContainer}>
                        <ResponsiveContainer width="100%" height={200}>
                            <BarChart data={fraudData} layout="vertical">
                                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                                <XAxis type="number" tick={{ fill: '#8b96a9', fontSize: 11 }} />
                                <YAxis type="category" dataKey="name" tick={{ fill: '#c4cdd8', fontSize: 11 }} width={160} />
                                <Tooltip
                                    contentStyle={{ background: '#0e0e24', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8, color: '#e8edf5' }}
                                />
                                <Bar dataKey="count" radius={[0, 6, 6, 0]}>
                                    {fraudData.map((_, idx) => (
                                        <Cell key={idx} fill={['#f87171', '#fbbf24', '#818cf8'][idx]} />
                                    ))}
                                </Bar>
                            </BarChart>
                        </ResponsiveContainer>
                    </div>
                </div>

                {/* Manager Rejection Breakdown */}
                {stats.manager_rejections?.by_category && Object.keys(stats.manager_rejections.by_category).length > 0 && (
                    <div style={s.section} role="region" aria-label="Manager Rejection Statistics">
                        <h3 style={s.sectionTitle}>🛑 Manager Rejections by Category</h3>
                        <div style={s.chartContainer}>
                            <ResponsiveContainer width="100%" height={220}>
                                <BarChart
                                    data={Object.entries(stats.manager_rejections.by_category).map(([name, count]) => ({
                                        name, count,
                                    }))}
                                    layout="vertical"
                                >
                                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                                    <XAxis type="number" tick={{ fill: '#8b96a9', fontSize: 11 }} />
                                    <YAxis type="category" dataKey="name" tick={{ fill: '#c4cdd8', fontSize: 10 }} width={180} />
                                    <Tooltip
                                        contentStyle={{ background: '#0e0e24', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8, color: '#e8edf5' }}
                                    />
                                    <Bar dataKey="count" fill="#f87171" radius={[0, 6, 6, 0]} />
                                </BarChart>
                            </ResponsiveContainer>
                        </div>
                    </div>
                )}

                <div style={s.timestamp}>
                    Generated at: {stats.generated_at ? new Date(stats.generated_at).toLocaleString() : '—'}
                </div>
            </div>
        </div>
    );
}
