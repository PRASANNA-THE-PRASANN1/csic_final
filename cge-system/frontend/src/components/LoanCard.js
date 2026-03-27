import React from 'react';

export default function LoanCard({ loan, onClick, selected }) {
    const formatINR = (v) =>
        new Intl.NumberFormat('en-IN', {
            style: 'currency',
            currency: 'INR',
            maximumFractionDigits: 0,
        }).format(v);

    return (
        <div
            className={`loan-card ${selected ? 'selected' : ''}`}
            onClick={onClick}
        >
            <div className="loan-card-row">
                <span className="loan-card-id">{loan.loan_id}</span>
                <span className={`status-badge status-${loan.status}`}>
                    {loan.status?.replace(/_/g, ' ')}
                </span>
            </div>
            <div className="loan-card-row">
                <span className="loan-card-farmer">🌾 {loan.farmer_name}</span>
                <span className="loan-card-amount">{formatINR(loan.amount)}</span>
            </div>
            <div className="loan-card-row">
                <span className="loan-card-tier">{loan.approval_tier?.toUpperCase()}</span>
                <span className="loan-card-purpose">{loan.purpose?.slice(0, 35)}...</span>
            </div>
        </div>
    );
}
