// Agent Avatar with personality-based styling

// Personality color schemes
const personalityColors = {
    efficiency: {
        primary: '#3B82F6',
        secondary: '#06B6D4',
        pattern: 'sharp'
    },
    equality: {
        primary: '#10B981',
        secondary: '#14B8A6',
        pattern: 'rounded'
    },
    freedom: {
        primary: '#8B5CF6',
        secondary: '#EC4899',
        pattern: 'dynamic'
    },
    stability: {
        primary: '#F59E0B',
        secondary: '#78350F',
        pattern: 'solid'
    },
    neutral: {
        primary: '#6B7280',
        secondary: '#9CA3AF',
        pattern: 'balanced'
    }
}

// Tier gradient overlays
const tierGradients = {
    1: 'linear-gradient(135deg, rgba(245, 158, 11, 0.2) 0%, rgba(245, 158, 11, 0.1) 100%)',
    2: 'linear-gradient(135deg, rgba(139, 92, 246, 0.2) 0%, rgba(139, 92, 246, 0.1) 100%)',
    3: 'linear-gradient(135deg, rgba(59, 130, 246, 0.2) 0%, rgba(59, 130, 246, 0.1) 100%)',
    4: 'linear-gradient(135deg, rgba(107, 114, 128, 0.2) 0%, rgba(107, 114, 128, 0.1) 100%)'
}

// Generate a deterministic pattern based on agent number
function generatePattern(agentNumber, personality) {
    const colors = personalityColors[personality] || personalityColors.neutral
    const pattern = colors.pattern

    // Create unique hue shift based on agent number
    const hueShift = (agentNumber * 7) % 30 - 15

    return {
        pattern,
        hueShift,
        colors
    }
}

export default function AgentAvatar({
    agentNumber,
    tier = 3,
    personality = 'neutral',
    size = 'medium', // 'small', 'medium', 'large'
    status = 'active',
    showNumber = true,
    className = ''
}) {
    const { colors, pattern, hueShift } = generatePattern(agentNumber, personality)

    const sizeClasses = {
        small: 'avatar-sm',
        medium: 'avatar-md',
        large: 'avatar-lg'
    }

    const avatarStyle = {
        '--primary-color': colors.primary,
        '--secondary-color': colors.secondary,
        '--tier-gradient': tierGradients[tier],
        '--hue-shift': `${hueShift}deg`
    }

    return (
        <div
            className={`agent-avatar ${sizeClasses[size]} tier-${tier} ${pattern} ${status} ${className}`}
            style={avatarStyle}
        >
            {/* Pattern overlay based on personality */}
            <div className="avatar-pattern" />

            {/* Tier indicator ring */}
            <div className="avatar-tier-ring" />

            {/* Agent number */}
            {showNumber && (
                <span className="avatar-number">
                    #{agentNumber}
                </span>
            )}

            {/* Status indicator */}
            {status === 'dormant' && (
                <div className="avatar-dormant-overlay" />
            )}
        </div>
    )
}

// Simple text avatar for compact views
export function AgentAvatarCompact({ agentNumber, tier = 3, className = '' }) {
    return (
        <div className={`agent-avatar-compact tier-${tier} ${className}`}>
            #{agentNumber}
        </div>
    )
}

// Personality badge
export function PersonalityBadge({ personality, showIcon = true }) {
    const colors = personalityColors[personality] || personalityColors.neutral

    const icons = {
        efficiency: '⚡',
        equality: '⚖️',
        freedom: '🦅',
        stability: '🏛️',
        neutral: '⚪'
    }

    return (
        <span
            className="personality-badge"
            style={{ '--badge-color': colors.primary }}
        >
            {showIcon && <span className="personality-icon">{icons[personality]}</span>}
            <span className="personality-name">{personality}</span>
        </span>
    )
}
