function formatModeList(modes, labels) {
    if (!Array.isArray(modes) || modes.length === 0) return 'none'
    return modes
        .map((mode) => labels?.[mode] || String(mode || '').replace(/_/g, ' '))
        .filter(Boolean)
        .join(', ')
}

export default function ReserveSemanticsNote({ semantics, compact = false }) {
    if (!semantics) return null

    const policy = semantics.policy_intent || {}
    const mechanical = semantics.mechanical_access || {}
    const labels = mechanical.mode_labels || {}
    const policyLabel = semantics.policy_intent_label || policy.label || 'Reserve policy intent'
    const mechanicalLabel = semantics.mechanical_access_label || mechanical.label || 'Reserve mechanical access'
    const enabledModes = formatModeList(mechanical.enabled_modes, labels)
    const disabledModes = formatModeList(mechanical.disabled_modes, labels)

    return (
        <div className="reserve-semantics-note">
            <div>
                <strong>Policy intent:</strong> {policyLabel}
            </div>
            <div>
                <strong>Mechanical access:</strong> {mechanicalLabel}
            </div>
            {!compact && (
                <div className="reserve-gate-list">
                    <span>Enabled gates: {enabledModes}</span>
                    <span>Disabled gates: {disabledModes}</span>
                </div>
            )}
        </div>
    )
}
