// Skeleton loading components for perceived performance
import './Skeleton.css'

export function SkeletonCard({ className = '' }) {
    return (
        <div className={`skeleton-card ${className}`}>
            <div className="skeleton-header">
                <div className="skeleton skeleton-avatar"></div>
                <div className="skeleton-info">
                    <div className="skeleton skeleton-title"></div>
                    <div className="skeleton skeleton-subtitle"></div>
                </div>
            </div>
            <div className="skeleton-body">
                <div className="skeleton skeleton-line"></div>
                <div className="skeleton skeleton-line short"></div>
            </div>
        </div>
    )
}

export function SkeletonStatCard() {
    return (
        <div className="skeleton-stat-card">
            <div className="skeleton-header">
                <div className="skeleton skeleton-label"></div>
                <div className="skeleton skeleton-icon"></div>
            </div>
            <div className="skeleton skeleton-value"></div>
            <div className="skeleton skeleton-bar"></div>
        </div>
    )
}

export function SkeletonEventCard() {
    return (
        <div className="skeleton-event">
            <div className="skeleton skeleton-event-icon"></div>
            <div className="skeleton-event-content">
                <div className="skeleton skeleton-line"></div>
                <div className="skeleton skeleton-line short"></div>
            </div>
        </div>
    )
}

export function SkeletonAgentCard() {
    return (
        <div className="skeleton-agent-card">
            <div className="skeleton-header">
                <div className="skeleton skeleton-avatar"></div>
                <div className="skeleton-info">
                    <div className="skeleton skeleton-title"></div>
                    <div className="skeleton skeleton-subtitle"></div>
                </div>
            </div>
            <div className="skeleton-stats">
                <div className="skeleton skeleton-stat-item"></div>
                <div className="skeleton skeleton-stat-item"></div>
                <div className="skeleton skeleton-stat-item"></div>
            </div>
        </div>
    )
}

export function SkeletonTable({ rows = 5, cols = 4 }) {
    return (
        <div className="skeleton-table">
            <div className="skeleton-table-header">
                {Array.from({ length: cols }).map((_, i) => (
                    <div key={i} className="skeleton skeleton-th"></div>
                ))}
            </div>
            {Array.from({ length: rows }).map((_, rowIndex) => (
                <div key={rowIndex} className="skeleton-table-row">
                    {Array.from({ length: cols }).map((_, colIndex) => (
                        <div key={colIndex} className="skeleton skeleton-td"></div>
                    ))}
                </div>
            ))}
        </div>
    )
}

export default {
    Card: SkeletonCard,
    StatCard: SkeletonStatCard,
    EventCard: SkeletonEventCard,
    AgentCard: SkeletonAgentCard,
    Table: SkeletonTable,
}
