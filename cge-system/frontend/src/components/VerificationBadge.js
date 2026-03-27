import React from 'react';

const STATUS_CONFIG = {
    valid: { icon: '✅', label: 'Valid', className: 'badge-valid' },
    invalid: { icon: '❌', label: 'Invalid', className: 'badge-invalid' },
    pending: { icon: '⏳', label: 'Pending', className: 'badge-pending' },
    missing: { icon: '⚠️', label: 'Missing', className: 'badge-missing' },
    not_anchored: { icon: '🔗', label: 'Not Anchored', className: 'badge-pending' },
    error: { icon: '💥', label: 'Error', className: 'badge-invalid' },
};

export default function VerificationBadge({ status }) {
    const config = STATUS_CONFIG[status] || STATUS_CONFIG.pending;

    return (
        <span className={`verification-badge ${config.className}`}>
            {config.icon} {config.label}
        </span>
    );
}
