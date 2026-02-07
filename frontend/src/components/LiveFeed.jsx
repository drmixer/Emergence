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

const sociallySalientEventTypes = new Set([
    'forum_post',
    'forum_reply',
    'direct_message',
    'create_proposal',
    'proposal_created',
    'vote',
    'law_passed',
    'trade',
    'became_dormant',
    'awakened',
    'agent_revived',
    'agent_died',
    'faction_formed',
    'crisis',
    'world_event',
    'daily_summary',
    'enforcement_initiated',
    'vote_enforcement',
    'resources_seized',
    'agent_sanctioned',
    'agent_exiled',
    'set_name',
])

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
                    <span className="event-time">{timeAgo}</span>
                </div>
            </div>
        </div>
    )
}

export default function LiveFeed() {
    const [events, setEvents] = useState([])
    const [showBackground, setShowBackground] = useState(false)
    const [showSystemNoise, setShowSystemNoise] = useState(false)
    const [showHiddenControls, setShowHiddenControls] = useState(false)
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
            return sociallySalientEventTypes.has(t)
        })
    }, [events, showBackground, showSystemNoise])

    const hiddenCounts = useMemo(() => {
        let bg = 0
        let system = 0
        for (const e of events) {
            const t = e?.event_type
            if (!t) continue
            if (!showBackground && backgroundEventTypes.has(t)) bg += 1
            if (!showSystemNoise && noisyEventTypes.has(t)) system += 1
        }
        return { bg, system }
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

            {(hiddenCounts.bg > 0 || hiddenCounts.system > 0) && (
                <div
                    className="feed-notice"
                    style={{ cursor: 'pointer', userSelect: 'none' }}
                    onClick={() => setShowHiddenControls((v) => !v)}
                    title="Show/hide controls for background + system events"
                >
                    Hidden: {hiddenCounts.bg} bg, {hiddenCounts.system} system
                </div>
            )}

            {showHiddenControls && (
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
            )}

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
