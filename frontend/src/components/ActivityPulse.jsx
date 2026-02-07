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
    const [pulseActive, setPulseActive] = useState(true)
    const [displayCount, setDisplayCount] = useState(messageCount)

    // Animate the message count when it changes
    useEffect(() => {
        if (messageCount > displayCount) {
            const difference = messageCount - displayCount
            const increment = Math.ceil(difference / 20)
            const timer = setInterval(() => {
                setDisplayCount(prev => {
                    const next = prev + increment
                    if (next >= messageCount) {
                        clearInterval(timer)
                        return messageCount
                    }
                    return next
                })
            }, 50)
            return () => clearInterval(timer)
        } else {
            setDisplayCount(messageCount)
        }
    }, [messageCount])

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
