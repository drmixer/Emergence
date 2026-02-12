// Agent Avatar with personality-based styling
import './AgentAvatar.css'

const patterns = ['sharp', 'rounded', 'dynamic', 'solid', 'balanced']
const shapeClasses = ['shape-square', 'shape-round', 'shape-pill', 'shape-hex', 'shape-cut']
const tierRingColors = {
    1: 'rgba(245, 158, 11, 0.45)',
    2: 'rgba(59, 130, 246, 0.45)',
    3: 'rgba(34, 197, 94, 0.45)',
    4: 'rgba(148, 163, 184, 0.42)',
}
const personalityColors = {
    efficiency: '#3b82f6',
    equality: '#10b981',
    freedom: '#8b5cf6',
    stability: '#f59e0b',
    neutral: '#6b7280',
}

function safeAgentNumber(agentNumber) {
    const parsed = Number(agentNumber)
    if (!Number.isFinite(parsed) || parsed <= 0) return 1
    return Math.trunc(parsed)
}

// Generate deterministic but unique visual identity from canonical agent number.
function generateAvatarIdentity(agentNumber, personality, tier = 3) {
    const safe = safeAgentNumber(agentNumber)
    const hue = (safe * 137) % 360
    const secondaryHue = (hue + 42) % 360
    const pattern = patterns[(safe - 1) % patterns.length]
    const shapeClass = shapeClasses[(safe * 3) % shapeClasses.length]
    const accent = personalityColors[personality] || personalityColors.neutral
    const tierKey = Number(tier) >= 1 && Number(tier) <= 4 ? Number(tier) : 4

    return {
        pattern,
        shapeClass,
        safe,
        style: {
            '--primary-color': `hsl(${hue} 74% 58%)`,
            '--secondary-color': `hsl(${secondaryHue} 78% 64%)`,
            '--avatar-bg': `linear-gradient(135deg, hsl(${hue} 64% 30%) 0%, hsl(${secondaryHue} 70% 18%) 100%)`,
            '--avatar-border': `hsla(${hue} 90% 72% / 0.55)`,
            '--tier-ring-color': tierRingColors[tierKey] || tierRingColors[4],
            '--personality-accent': accent,
            '--compact-bg': `hsla(${hue} 84% 58% / 0.15)`,
            '--compact-border': `hsla(${hue} 84% 58% / 0.45)`,
            '--compact-text': `hsl(${hue} 85% 68%)`,
        },
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
    const avatarIdentity = generateAvatarIdentity(agentNumber, personality, tier)

    const sizeClasses = {
        small: 'avatar-sm',
        medium: 'avatar-md',
        large: 'avatar-lg'
    }

    return (
        <div
            className={`agent-avatar ${sizeClasses[size]} tier-${tier} ${avatarIdentity.pattern} ${avatarIdentity.shapeClass} ${status} ${className}`}
            style={avatarIdentity.style}
        >
            {/* Pattern overlay based on personality */}
            <div className="avatar-pattern" />

            {/* Tier indicator ring */}
            <div className="avatar-tier-ring" />

            {/* Agent number */}
            {showNumber && (
                <span className="avatar-number">
                    #{avatarIdentity.safe}
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
    const avatarIdentity = generateAvatarIdentity(agentNumber, 'neutral', tier)
    return (
        <div
            className={`agent-avatar-compact tier-${tier} ${className}`}
            style={avatarIdentity.style}
        >
            #{avatarIdentity.safe}
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
            style={{ '--badge-color': colors }}
        >
            {showIcon && <span className="personality-icon">{icons[personality]}</span>}
            <span className="personality-name">{personality}</span>
        </span>
    )
}
