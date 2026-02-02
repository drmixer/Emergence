// Resource Bar with anxiety indicators
import { AlertTriangle, TrendingDown } from 'lucide-react'
import './ResourceBar.css'

// Get color based on resource level (percentage)
function getResourceLevel(current, max) {
    const percentage = (current / max) * 100
    if (percentage >= 60) return 'healthy'
    if (percentage >= 40) return 'warning'
    if (percentage >= 20) return 'danger'
    return 'critical'
}

export function ResourceBar({
    label,
    current,
    max,
    icon: Icon,
    type = 'food', // food, energy, materials
    showWarning = true
}) {
    const percentage = Math.min(100, (current / max) * 100)
    const level = getResourceLevel(current, max)
    const isCritical = level === 'critical' || level === 'danger'

    return (
        <div className={`resource-bar-container ${level} ${isCritical ? 'pulse-warning' : ''}`}>
            <div className="resource-bar-header">
                <div className="resource-bar-label">
                    {Icon && <Icon size={16} />}
                    <span>{label}</span>
                </div>
                <div className="resource-bar-value">
                    <span className="current">{current.toLocaleString()}</span>
                    <span className="separator">/</span>
                    <span className="max">{max.toLocaleString()}</span>
                </div>
            </div>

            <div className="resource-bar-track">
                <div
                    className={`resource-bar-fill ${type} ${level}`}
                    style={{ width: `${percentage}%` }}
                >
                    {isCritical && <div className="bar-pulse" />}
                </div>
            </div>

            {showWarning && isCritical && (
                <div className="resource-warning">
                    <AlertTriangle size={12} />
                    <span>
                        {level === 'critical'
                            ? 'Critical! Agents at risk'
                            : 'Low resources - attention needed'}
                    </span>
                </div>
            )}
        </div>
    )
}

// Warning banner for critical agents
export function CriticalAgentsBanner({ count, type = 'food' }) {
    if (count === 0) return null

    return (
        <div className="critical-banner">
            <AlertTriangle size={16} />
            <span>
                <strong>⚠️ {count} agent{count > 1 ? 's' : ''}</strong> at critical {type} levels
            </span>
            <TrendingDown size={14} className="trend-icon" />
        </div>
    )
}

// Countdown timer for next consumption cycle
export function ConsumptionCountdown({ nextCycleTime }) {
    // Calculate time remaining
    const now = new Date()
    const target = new Date(nextCycleTime)
    const diff = target - now

    if (diff <= 0) {
        return (
            <div className="consumption-countdown imminent">
                <span>⚡ Consumption cycle in progress...</span>
            </div>
        )
    }

    const hours = Math.floor(diff / (1000 * 60 * 60))
    const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60))
    const seconds = Math.floor((diff % (1000 * 60)) / 1000)

    const isUrgent = diff < 1000 * 60 * 30 // Less than 30 minutes

    return (
        <div className={`consumption-countdown ${isUrgent ? 'urgent' : ''}`}>
            <span className="countdown-label">Next consumption cycle in</span>
            <span className="countdown-time">
                {hours.toString().padStart(2, '0')}:
                {minutes.toString().padStart(2, '0')}:
                {seconds.toString().padStart(2, '0')}
            </span>
        </div>
    )
}

export default ResourceBar
