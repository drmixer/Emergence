import { useState, useEffect, useCallback, useMemo } from 'react'
import { Link } from 'react-router-dom'
import { formatDistanceToNow } from 'date-fns'
import {
    Zap,
    MessageSquare,
    Vote,
    Briefcase,
    ArrowRightLeft,
    AlertCircle,
    User,
    FileText,
    ShieldCheck,
    Twitter
} from 'lucide-react'
import { api, subscribeToEvents } from '../services/api'
import { showEventToast } from './ToastNotifications'

const backgroundEventTypes = new Set(['work', 'idle'])
const noisyEventTypes = new Set(['invalid_action', 'processing_error'])
const directThreadEventTypes = new Set([
    'direct_message',
    'request_aid',
    'aid_request_received',
    'refuse_aid',
    'aid_refusal_received',
])
const forumThreadEventTypes = new Set([
    'forum_post',
    'forum_reply',
    'public_accusation',
])
const agentStatusEventTypes = new Set(['became_dormant', 'awakened', 'agent_died', 'agent_revived'])

const eventIcons = {
    forum_post: MessageSquare,
    forum_reply: MessageSquare,
    direct_message: MessageSquare,
    create_proposal: FileText,
    vote: Vote,
    work: Briefcase,
    trade: ArrowRightLeft,
    request_aid: AlertCircle,
    refuse_aid: AlertCircle,
    reserve_aid: ShieldCheck,
    tweet_posted: Twitter,
    became_dormant: AlertCircle,
    agent_revived: Zap,
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
    request_aid: 'red',
    refuse_aid: 'red',
    reserve_aid: 'green',
    tweet_posted: 'blue',
    became_dormant: 'red',
    agent_revived: 'green',
    awakened: 'green',
    set_name: 'purple',
    default: 'blue',
}

function formatDirectMessageDescription(event) {
    const metadata = event?.metadata && typeof event.metadata === 'object' ? event.metadata : {}
    const result = metadata?.result && typeof metadata.result === 'object' ? metadata.result : {}
    const authorName = String(result.author_name || '').trim()
    const recipientName = String(result.recipient_name || '').trim()
    const preview = String(result.content_preview || '').trim()

    if (!authorName || !recipientName) {
        return String(event?.description || '').trim()
    }

    const headline = `${authorName} -> ${recipientName}`
    if (!preview) {
        return headline
    }
    return `${headline}: ${preview}`
}

function getEventDescription(event) {
    const eventType = String(event?.event_type || '').trim()
    const metadata = event?.metadata && typeof event.metadata === 'object' ? event.metadata : {}
    if (eventType === 'direct_message') {
        return formatDirectMessageDescription(event)
    }
    if (eventType === 'tweet_posted') {
        const quoteText = String(metadata.quote_text || '').trim()
        if (quoteText) {
            return `${String(event?.description || '').trim()}: "${quoteText}"`
        }
    }
    if (eventType === 'work') {
        const description = String(event?.description || '').trim()
        const match = description.match(/^(.*?) worked (\d+(?:\.\d+)?)h (\w+), produced ([\d.]+) (\w+)/i)
        if (match) {
            const [, name, hours, workLabel, amount, resource] = match
            const cleanVerb = {
                generating: 'generated',
                gathering: 'gathered',
                farming: 'farmed',
            }[String(workLabel || '').toLowerCase()] || 'produced'
            return `${name} ${cleanVerb} ${amount} ${resource} in ${hours}h`
        }
    }
    return String(event?.description || '').trim()
}

function isDegradedFallbackEvent(event) {
    return Boolean(event?.is_degraded_fallback)
}

function getContinuityOrigin(payload) {
    const origin = String(payload?.lineage_origin || '').trim().toLowerCase()
    return origin === 'carryover' || origin === 'fresh' ? origin : ''
}

function getMessageThreadId(event) {
    const metadata = event?.metadata && typeof event.metadata === 'object' ? event.metadata : {}
    const result = metadata?.result && typeof metadata.result === 'object' ? metadata.result : {}
    const direct = Number(result.message_id || metadata.message_id || 0)
    return Number.isFinite(direct) && direct > 0 ? direct : 0
}

function getEventRunId(event) {
    const metadata = event?.metadata && typeof event.metadata === 'object' ? event.metadata : {}
    const runtime = metadata?.runtime && typeof metadata.runtime === 'object' ? metadata.runtime : {}
    return String(runtime.run_id || metadata.run_id || '').trim()
}

function getEventHref(event) {
    const eventType = String(event?.event_type || '').trim()
    const agentNumber = Number(event?.agent_number || 0)
    const threadId = getMessageThreadId(event)

    if (
        threadId > 0 &&
        directThreadEventTypes.has(eventType)
    ) {
        return `/messages?tab=direct&thread=${threadId}`
    }

    if (
        threadId > 0 &&
        forumThreadEventTypes.has(eventType)
    ) {
        return `/messages?tab=forum&thread=${threadId}`
    }

    if (eventType === 'create_proposal') {
        return '/governance?tab=proposals'
    }

    if (eventType === 'law_passed' || eventType === 'vote' || eventType === 'proposal_resolved') {
        return '/governance'
    }

    if (eventType === 'trade' || eventType === 'request_aid' || eventType === 'reserve_aid') {
        return '/resources'
    }

    if (agentNumber > 0 && agentStatusEventTypes.has(eventType)) {
        return `/agents/${agentNumber}`
    }

    const eventId = Number(event?.id || 0)
    const runId = getEventRunId(event)
    if (eventId > 0 && runId) {
        return `/runs/${encodeURIComponent(runId)}?event=${encodeURIComponent(String(eventId))}`
    }
    return eventId > 0 ? `/timeline?event=${eventId}` : ''
}

function EventCard({ event }) {
    const Icon = eventIcons[event.event_type] || eventIcons.default
    const color = eventColors[event.event_type] || eventColors.default
    const href = getEventHref(event)

    const timeAgo = event.created_at
        ? formatDistanceToNow(new Date(event.created_at), { addSuffix: true })
        : 'just now'
    const description = getEventDescription(event)

    const body = (
        <div className={`event-card animate-fade-in`}>
            <div className={`event-icon ${color}`}>
                <Icon size={16} />
            </div>
            <div className="event-content">
                <div className="event-description">{description}</div>
                <div className="event-meta">
                    <span className="event-type">{event.event_type.replace(/_/g, ' ')}</span>
                    {isDegradedFallbackEvent(event) && (
                        <span className="event-continuity-chip degraded">Degraded fallback</span>
                    )}
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

    if (!href) {
        return body
    }

    return (
        <Link to={href} className="event-card-link">
            {body}
        </Link>
    )
}

export default function LiveFeed() {
    const [events, setEvents] = useState([])
    const [showMeaningful, setShowMeaningful] = useState(true)
    const [showBackground, setShowBackground] = useState(false)
    const [showSystemNoise, setShowSystemNoise] = useState(false)
    const [connected, setConnected] = useState(false)
    const [error, setError] = useState(null)
    const [runState, setRunState] = useState('checking')
    const [lastCompletedRunId, setLastCompletedRunId] = useState('')

    const addEvent = useCallback((newEvent) => {
        setEvents(prev => [newEvent, ...prev].slice(0, 100))
        setRunState('live')

        // Show toast notification for notable events
        showEventToast(newEvent)
    }, [])

    const refreshRunState = useCallback(async () => {
        try {
            const overview = await api.getAnalyticsOverview()
            const scope = overview?.scope && typeof overview.scope === 'object' ? overview.scope : {}
            const completedRunId = String(scope.last_completed_run_id || '').trim()
            const simulationActive = scope.simulation_active === true

            setLastCompletedRunId(completedRunId)
            setRunState(simulationActive ? 'live' : completedRunId ? 'idle' : 'prelaunch')
        } catch {
            setRunState((current) => (current === 'checking' ? 'prelaunch' : current))
        }
    }, [])

    const visibleEvents = useMemo(() => {
        return events.filter((e) => {
            const t = e.event_type
            if (!t) return false
            if (backgroundEventTypes.has(t)) return showBackground
            if (noisyEventTypes.has(t)) return showSystemNoise
            return showMeaningful
        })
    }, [events, showBackground, showMeaningful, showSystemNoise])

    useEffect(() => {
        const initialRefreshTimer = window.setTimeout(() => {
            void refreshRunState()
        }, 0)

        // Try to connect to SSE
        const unsubscribe = subscribeToEvents(
            (event) => {
                if (event.type === 'connected') {
                    setConnected(true)
                    setError(null)
                } else if (event.type === 'snapshot_empty') {
                    setEvents([])
                    void refreshRunState()
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
            window.clearTimeout(initialRefreshTimer)
            unsubscribe()
        }
    }, [addEvent, refreshRunState])

    if (events.length === 0 && runState !== 'live') {
        const isIdle = runState === 'idle'
        const isChecking = runState === 'checking'
        return (
            <div className="live-feed">
                <div className="live-feed-header">
                    <h3>Live Feed</h3>
                    <div className={`live-indicator ${isIdle ? 'disconnected' : 'waiting'}`}>
                        {isChecking ? 'Checking' : isIdle ? 'Idle' : 'Waiting'}
                    </div>
                </div>

                <div className="feed-prelaunch">
                    <div className="prelaunch-icon">
                        <Zap size={32} />
                    </div>
                    <h4>
                        {isChecking
                            ? 'Checking feed status'
                            : isIdle
                                ? 'No run in progress'
                                : 'Waiting for Experiment'}
                    </h4>
                    <p>
                        {isChecking
                            ? 'Loading the current run state.'
                            : isIdle
                                ? 'Live events will appear here when the next run starts.'
                                : "The simulation hasn't started yet. Events will appear here once agents begin interacting."}
                    </p>
                    {isIdle && lastCompletedRunId ? (
                        <p>
                            Last completed run:{' '}
                            <Link to={`/runs/${encodeURIComponent(lastCompletedRunId)}`}>
                                {lastCompletedRunId}
                            </Link>
                        </p>
                    ) : (
                        <div className="prelaunch-dots">
                            <span></span>
                            <span></span>
                            <span></span>
                        </div>
                    )}
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

            <div className="feed-layer-controls" aria-label="Live feed event layers">
                <label className="feed-layer-toggle">
                    <input
                        type="checkbox"
                        checked={showMeaningful}
                        onChange={(e) => setShowMeaningful(e.target.checked)}
                    />
                    Meaningful events
                </label>
                <label className="feed-layer-toggle">
                    <input
                        type="checkbox"
                        checked={showBackground}
                        onChange={(e) => setShowBackground(e.target.checked)}
                    />
                    Routine/raw events
                </label>
                <label className="feed-layer-toggle">
                    <input
                        type="checkbox"
                        checked={showSystemNoise}
                        onChange={(e) => setShowSystemNoise(e.target.checked)}
                    />
                    System diagnostics
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
                        <p>No events in selected layers.</p>
                    </div>
                )}
            </div>
        </div>
    )
}
