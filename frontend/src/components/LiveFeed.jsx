import { useState, useEffect, useCallback, useMemo } from 'react'
import { formatDistanceToNow } from 'date-fns'
import {
    Zap,
    MessageSquare,
    Vote,
    Briefcase,
    ArrowRightLeft,
    AlertCircle,
    User,
    FileText
} from 'lucide-react'
import { subscribeToEvents } from '../services/api'
import { showEventToast } from './ToastNotifications'

const backgroundEventTypes = new Set(['work', 'idle'])
const noisyEventTypes = new Set(['invalid_action', 'processing_error'])

const eventIcons = {
    forum_post: MessageSquare,
    forum_reply: MessageSquare,
    direct_message: MessageSquare,
    create_proposal: FileText,
    vote: Vote,
    work: Briefcase,
    trade: ArrowRightLeft,
    became_dormant: AlertCircle,
    awakened: Zap,
    set_name: User,
    default: Zap,
}

const eventColors = {
    forum_post: 'blue',
    forum_reply: 'blue',
    direct_message: 'purple',
    create_proposal: 'orange',
    vote: 'green',
    work: 'cyan',
    trade: 'yellow',
    became_dormant: 'red',
    awakened: 'green',
    set_name: 'purple',
    default: 'blue',
}

function getContinuityOrigin(payload) {
    const origin = String(payload?.lineage_origin || '').trim().toLowerCase()
    return origin === 'carryover' || origin === 'fresh' ? origin : ''
}

function EventCard({ event }) {
    const Icon = eventIcons[event.event_type] || eventIcons.default
    const color = eventColors[event.event_type] || eventColors.default

    const timeAgo = event.created_at
        ? formatDistanceToNow(new Date(event.created_at), { addSuffix: true })
        : 'just now'

    return (
        <div className={`event-card animate-fade-in`}>
            <div className={`event-icon ${color}`}>
                <Icon size={16} />
            </div>
            <div className="event-content">
                <div className="event-description">{event.description}</div>
                <div className="event-meta">
                    <span className="event-type">{event.event_type.replace(/_/g, ' ')}</span>
                    {getContinuityOrigin(event) === 'carryover' && (
                        <span className="event-continuity-chip carryover">Carryover</span>
                    )}
                    {getContinuityOrigin(event) === 'fresh' && (
                        <span className="event-continuity-chip fresh">Fresh</span>
                    )}
                    <span className="event-time">{timeAgo}</span>
                </div>
            </div>
        </div>
    )
}

export default function LiveFeed() {
    const [events, setEvents] = useState([])
    const [showBackground, setShowBackground] = useState(true)
    const [showSystemNoise, setShowSystemNoise] = useState(true)
    const [connected, setConnected] = useState(false)
    const [error, setError] = useState(null)
    const [isPreLaunch, setIsPreLaunch] = useState(true)

    const addEvent = useCallback((newEvent) => {
        setEvents(prev => [newEvent, ...prev].slice(0, 100))
        setIsPreLaunch(false) // Real events mean we're live

        // Show toast notification for notable events
        showEventToast(newEvent)
    }, [])

    const visibleEvents = useMemo(() => {
        return events.filter((e) => {
            const t = e.event_type
            if (!t) return false
            if (backgroundEventTypes.has(t)) return showBackground
            if (noisyEventTypes.has(t)) return showSystemNoise
            return true
        })
    }, [events, showBackground, showSystemNoise])

    useEffect(() => {
        // Try to connect to SSE
        const unsubscribe = subscribeToEvents(
            (event) => {
                if (event.type === 'connected') {
                    setConnected(true)
                    setError(null)
                } else if (event.type === 'event') {
                    addEvent(event)
                }
            },
            () => {
                setConnected(false)
                setError('Connection lost.')
            }
        )

        return () => {
            unsubscribe()
        }
    }, [addEvent])

    // Pre-launch waiting state
    if (isPreLaunch && events.length === 0) {
        return (
            <div className="live-feed">
                <div className="live-feed-header">
                    <h3>Live Feed</h3>
                    <div className="live-indicator waiting">
                        Waiting
                    </div>
                </div>

                <div className="feed-prelaunch">
                    <div className="prelaunch-icon">
                        <Zap size={32} />
                    </div>
                    <h4>Waiting for Experiment</h4>
                    <p>The simulation hasn't started yet. Events will appear here once agents begin interacting.</p>
                    <div className="prelaunch-dots">
                        <span></span>
                        <span></span>
                        <span></span>
                    </div>
                </div>
            </div>
        )
    }

    return (
        <div className="live-feed">
            <div className="live-feed-header">
                <h3>Live Feed</h3>
                <div className={`live-indicator ${connected ? '' : 'disconnected'}`}>
                    {connected ? 'Live' : 'Demo'}
                </div>
            </div>

            <div className="feed-notice" style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
                <label style={{ display: 'flex', gap: 6, alignItems: 'center', cursor: 'pointer' }}>
                    <input
                        type="checkbox"
                        checked={showBackground}
                        onChange={(e) => setShowBackground(e.target.checked)}
                    />
                    Background
                </label>
                <label style={{ display: 'flex', gap: 6, alignItems: 'center', cursor: 'pointer' }}>
                    <input
                        type="checkbox"
                        checked={showSystemNoise}
                        onChange={(e) => setShowSystemNoise(e.target.checked)}
                    />
                    System
                </label>
            </div>

            {error && (
                <div className="feed-notice">
                    {error}
                </div>
            )}

            <div className="events-list">
                {visibleEvents.map((event, index) => (
                    <EventCard key={event.id || index} event={event} />
                ))}

                {visibleEvents.length === 0 && (
                    <div className="empty-feed">
                        <Zap size={24} />
                        <p>Waiting for events...</p>
                    </div>
                )}
            </div>
        </div>
    )
}
