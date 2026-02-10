// Activity Pulse - Shows the simulation is ALIVE
import { useState, useEffect } from 'react'
import { formatDistanceToNow } from 'date-fns'
import { Activity, Clock, TrendingUp } from 'lucide-react'

export default function ActivityPulse({
    isLive = true,
    lastActivity = null,
    messageCount = 0,
    dayNumber = 0
}) {
    const pulseActive = Boolean(isLive)
    const [displayCount, setDisplayCount] = useState(messageCount)

    // Animate the message count when it changes
    useEffect(() => {
        if (messageCount === displayCount) return undefined

        const direction = messageCount > displayCount ? 1 : -1
        const difference = Math.abs(messageCount - displayCount)
        const step = Math.max(1, Math.ceil(difference / 20)) * direction

        const timer = setInterval(() => {
            setDisplayCount(prev => {
                const next = prev + step
                const reachedTarget =
                    (direction > 0 && next >= messageCount) ||
                    (direction < 0 && next <= messageCount)
                if (reachedTarget) {
                    clearInterval(timer)
                    return messageCount
                }
                return next
            })
        }, 50)

        return () => clearInterval(timer)
    }, [displayCount, messageCount])

    // Calculate time ago
    const timeAgo = lastActivity
        ? formatDistanceToNow(new Date(lastActivity), { addSuffix: true })
        : 'waiting...'

    return (
        <div className={`activity-pulse ${isLive ? 'live' : 'offline'}`}>
            <div className="pulse-indicator">
                <div className={`pulse-dot ${pulseActive ? 'active' : ''}`}>
                    <Activity size={14} />
                </div>
                <span className="pulse-label">
                    {isLive ? 'LIVE' : 'OFFLINE'}
                </span>
            </div>

            <div className="pulse-stats">
                <div className="pulse-stat">
                    <Clock size={14} />
                    <span>Last action: {timeAgo}</span>
                </div>

                <div className="pulse-divider" />

                <div className="pulse-stat">
                    <TrendingUp size={14} />
                    <span className="pulse-count">{displayCount.toLocaleString()}</span>
                    <span>messages</span>
                </div>

                <div className="pulse-divider" />

                <div className="pulse-stat day">
                    <span className="day-label">Day</span>
                    <span className="day-value">{dayNumber}</span>
                </div>
            </div>
        </div>
    )
}
