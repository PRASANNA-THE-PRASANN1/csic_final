import React from 'react';

const ROLE_ORDER = ['branch_manager', 'regional_manager', 'credit_head', 'zonal_head'];
const ROLE_LABELS = {
    branch_manager: 'Branch Manager',
    regional_manager: 'Regional Manager',
    credit_head: 'Credit Head',
    zonal_head: 'Zonal Head',
};

export default function ApprovalFlow({ loan, approvalData }) {
    if (!approvalData) return null;

    const required = approvalData.required_approvals || [];
    const approvals = approvalData.approvals || [];
    const missing = approvalData.missing_approvals || [];

    const requiredRoles = required.map((r) => r.role);

    const getStatus = (role) => {
        const appr = approvals.find((a) => a.approver_role === role);
        if (appr) return 'approved';
        const isMissing = missing.find((m) => m.role === role);
        if (isMissing) return 'pending';
        return 'not_required';
    };

    const getApproverInfo = (role) => {
        return approvals.find((a) => a.approver_role === role);
    };

    return (
        <div className="approval-flow">
            <h4 className="flow-title">📋 Approval Progress</h4>
            <div className="flow-timeline">
                {ROLE_ORDER.filter((r) => requiredRoles.includes(r)).map((role, idx) => {
                    const status = getStatus(role);
                    const info = getApproverInfo(role);
                    return (
                        <div key={role} className={`flow-step flow-${status}`}>
                            <div className="flow-marker">
                                {status === 'approved' ? '✅' : status === 'pending' ? '⏳' : '○'}
                            </div>
                            <div className="flow-content">
                                <span className="flow-role">{ROLE_LABELS[role]}</span>
                                {info && (
                                    <span className="flow-approver">{info.approver_name}</span>
                                )}
                                {status === 'pending' && (
                                    <span className="flow-waiting">Awaiting...</span>
                                )}
                            </div>
                            {idx < requiredRoles.length - 1 && <div className="flow-connector" />}
                        </div>
                    );
                })}
            </div>

            <div className="flow-summary">
                {approvalData.approvals_complete ? (
                    <span className="flow-complete">✅ All approvals collected</span>
                ) : (
                    <span className="flow-pending">
                        ⏳ {approvalData.total_approvals || 0} of {required.length} approvals collected
                    </span>
                )}
            </div>
        </div>
    );
}
