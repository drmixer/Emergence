// Activity Pulse - Shows the simulation is ALIVE
import { useState, useEffect } from 'react'
import { formatDistanceToNow } from 'date-fns'
import { Activity, Clock, TrendingUp } from 'lucide-react'

function formatCycleCountdown(seconds) {
    if (seconds === null || seconds === undefined || !Number.isFinite(Number(seconds))) {
        return 'n/a'
    }
    const safe = Math.max(0, Math.floor(Number(seconds)))
    const hours = Math.floor(safe / 3600)
    const minutes = Math.floor((safe % 3600) / 60)
    const remainingSeconds = safe % 60

    if (hours > 0) {
        return `${hours}h ${minutes}m`
    }
    if (minutes > 0) {
        return `${minutes}m ${remainingSeconds.toString().padStart(2, '0')}s`
    }
    return `${remainingSeconds}s`
}

export default function ActivityPulse({
    isLive = true,
    lastActivity = null,
    messageCount = 0,
    dayNumber = 0,
    cycleStatus = null
}) {
    const pulseActive = Boolean(isLive)
    const [displayCount, setDisplayCount] = useState(messageCount)
    const [nowMs, setNowMs] = useState(() => Date.now())

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

    useEffect(() => {
        if (!cycleStatus?.enabled || !cycleStatus?.next_cycle_at) return undefined
        const timer = window.setInterval(() => setNowMs(Date.now()), 1000)
        return () => window.clearInterval(timer)
    }, [cycleStatus?.enabled, cycleStatus?.next_cycle_at])

    // Calculate time ago
    const timeAgo = lastActivity
        ? formatDistanceToNow(new Date(lastActivity), { addSuffix: true })
        : 'waiting...'
    const nextCycleAtMs = cycleStatus?.next_cycle_at
        ? new Date(cycleStatus.next_cycle_at).getTime()
        : null
    const secondsUntilNextCycle = Number.isFinite(nextCycleAtMs)
        ? Math.max(0, Math.ceil((nextCycleAtMs - nowMs) / 1000))
        : cycleStatus?.seconds_until_next_cycle
    const showCycleCountdown = Boolean(isLive && cycleStatus?.enabled)

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

                {showCycleCountdown && (
                    <>
                        <div className="pulse-divider" />

                        <div className="pulse-stat cycle">
                            <span className="day-label">Next cycle</span>
                            <span className="day-value">{formatCycleCountdown(secondsUntilNextCycle)}</span>
                        </div>
                    </>
                )}
            </div>
        </div>
    )
}
