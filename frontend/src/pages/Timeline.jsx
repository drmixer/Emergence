// Timeline Page - Visual history of simulation events
import { useState, useEffect, useMemo } from 'react'
import { Link } from 'react-router-dom'
import { formatDistanceToNow } from 'date-fns'
import {
    Calendar,
    MessageSquare,
    FileText,
    Scale,
    AlertTriangle,
    Users,
    Zap,
    TrendingUp,
    Gift,
    Moon,
    Sun,
    ChevronDown,
    ChevronUp,
    Filter
} from 'lucide-react'
import { api } from '../services/api'

// Event type configurations
const eventConfig = {
    forum_post: {
        icon: MessageSquare,
        color: '#3B82F6',
        label: 'Forum Post',
        major: true
    },
    forum_reply: {
        icon: MessageSquare,
        color: '#3B82F6',
        label: 'Forum Reply',
        major: false
    },
    direct_message: {
        icon: MessageSquare,
        color: '#8B5CF6',
        label: 'Direct Message',
        major: false
    },
    law_passed: {
        icon: Scale,
        color: '#10B981',
        label: 'Law Passed',
        major: true
    },
    vote: {
        icon: Scale,
        color: '#8B5CF6',
        label: 'Vote',
        major: false
    },
    proposal_created: {
        icon: FileText,
        color: '#3B82F6',
        label: 'Proposal Created',
        major: false
    },
    create_proposal: {
        icon: FileText,
        color: '#3B82F6',
        label: 'Proposal Created',
        major: false
    },
    trade: {
        icon: Gift,
        color: '#F59E0B',
        label: 'Trade',
        major: false
    },
    became_dormant: {
        icon: Moon,
        color: '#F59E0B',
        label: 'Agent Dormant',
        major: true
    },
    awakened: {
        icon: Sun,
        color: '#10B981',
        label: 'Agent Awakened',
        major: true
    },
    agent_revived: {
        icon: Sun,
        color: '#10B981',
        label: 'Agent Revived',
        major: true
    },
    agent_died: {
        icon: AlertTriangle,
        color: '#EF4444',
        label: 'Agent Died',
        major: true
    },
    crisis: {
        icon: Zap,
        color: '#EF4444',
        label: 'Crisis Event',
        major: true
    },
    milestone: {
        icon: TrendingUp,
        color: '#8B5CF6',
        label: 'Milestone',
        major: true
    },
    simulation_start: {
        icon: Gift,
        color: '#F59E0B',
        label: 'Simulation Started',
        major: true
    },
    faction_formed: {
        icon: Users,
        color: '#8B5CF6',
        label: 'Faction Formed',
        major: true
    },
    world_event: {
        icon: AlertTriangle,
        color: '#EF4444',
        label: 'World Event',
        major: true
    },
    daily_summary: {
        icon: TrendingUp,
        color: '#8B5CF6',
        label: 'Daily Summary',
        major: true
    },
    enforcement_initiated: {
        icon: Scale,
        color: '#EF4444',
        label: 'Enforcement',
        major: true
    },
    vote_enforcement: {
        icon: Scale,
        color: '#8B5CF6',
        label: 'Enforcement Vote',
        major: false
    },
    resources_seized: {
        icon: Gift,
        color: '#EF4444',
        label: 'Seizure',
        major: true
    },
    agent_sanctioned: {
        icon: AlertTriangle,
        color: '#F59E0B',
        label: 'Sanction',
        major: true
    },
    agent_exiled: {
        icon: AlertTriangle,
        color: '#EF4444',
        label: 'Exile',
        major: true
    },
    invalid_action: {
        icon: AlertTriangle,
        color: '#6B7280',
        label: 'Invalid Action',
        major: false
    },
    processing_error: {
        icon: AlertTriangle,
        color: '#6B7280',
        label: 'Processing Error',
        major: false
    },
    work: {
        icon: Zap,
        color: '#6B7280',
        label: 'Work',
        major: false
    },
    idle: {
        icon: Zap,
        color: '#6B7280',
        label: 'Idle',
        major: false
    },
    message: {
        icon: MessageSquare,
        color: '#6B7280',
        label: 'Message',
        major: false
    }
}

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
    'simulation_start',
    'milestone',
])

// Group events by day
function groupEventsByDay(events) {
    const grouped = {}

    events.forEach(event => {
        const day = event.day || 1
        if (!grouped[day]) {
            grouped[day] = []
        }
        grouped[day].push(event)
    })

    // Sort days in descending order (newest first)
    const sortedDays = Object.keys(grouped)
        .map(Number)
        .sort((a, b) => b - a)

    return { grouped, sortedDays }
}

export default function Timeline() {
    const [events, setEvents] = useState([])
    const [loading, setLoading] = useState(true)
    const [expandedDays, setExpandedDays] = useState({})
    const [filter, setFilter] = useState('all') // all, major, laws, agents
    const [currentDay, setCurrentDay] = useState(1)
    const [showBackground, setShowBackground] = useState(false)
    const [showSystemNoise, setShowSystemNoise] = useState(false)
    const [dayOverrides, setDayOverrides] = useState({})
    const [loadError, setLoadError] = useState(null)

    useEffect(() => {
        async function loadTimeline() {
            try {
                setLoadError(null)
                // Try to load real events
                const data = await api.getEvents({ limit: 500 })
                if (Array.isArray(data) && data.length > 0) {
                    // Compute an approximate day number for display (based on local timeline window).
                    const sorted = [...data].sort((a, b) => new Date(a.created_at) - new Date(b.created_at))
                    const base = new Date(sorted[0].created_at).getTime()
                    // Backend default is 1 real hour = 1 sim day.
                    const SIM_DAY_MS = 60 * 60 * 1000

                    const withDay = data.map((e) => {
                        const createdAtMs = new Date(e.created_at).getTime()
                        const day = Number.isFinite(createdAtMs)
                            ? Math.floor((createdAtMs - base) / SIM_DAY_MS) + 1
                            : 1
                        return { ...e, day }
                    })

                    const maxDay = Math.max(...withDay.map(e => e.day || 1))
                    setCurrentDay(maxDay)
                    setEvents(withDay)
                } else {
                    setEvents([])
                }
            } catch {
                setLoadError('Failed to load timeline events.')
                setEvents([])
            } finally {
                setLoading(false)
            }
        }

        loadTimeline()
    }, [])

    const hiddenCounts = useMemo(() => {
        const byDay = {}
        for (const e of events) {
            const day = e.day || 1
            if (!byDay[day]) byDay[day] = { work: 0, idle: 0, invalid_action: 0, processing_error: 0 }
            if (e.event_type in byDay[day]) byDay[day][e.event_type] += 1
        }
        return byDay
    }, [events])

    const { grouped: groupedAll, sortedDays } = useMemo(() => groupEventsByDay(events), [events])

    const matchesCategoryFilter = (event) => {
        switch (filter) {
            case 'major':
                return Boolean(eventConfig[event.event_type]?.major)
            case 'laws':
                return (
                    event.event_type === 'law_passed' ||
                    event.event_type === 'proposal_created' ||
                    event.event_type === 'create_proposal' ||
                    event.event_type === 'vote'
                )
            case 'agents':
                return (
                    event.event_type === 'became_dormant' ||
                    event.event_type === 'awakened' ||
                    event.event_type === 'faction_formed' ||
                    event.event_type === 'agent_revived' ||
                    event.event_type === 'agent_died'
                )
            default:
                return true
        }
    }

    const isVisibleForDay = (day, eventType) => {
        const override = dayOverrides[day] || {}
        const allowBackground = showBackground || Boolean(override.background)
        const allowNoise = showSystemNoise || Boolean(override.system)

        if (backgroundEventTypes.has(eventType)) return allowBackground
        if (noisyEventTypes.has(eventType)) return allowNoise
        return sociallySalientEventTypes.has(eventType)
    }

    const groupedVisible = useMemo(() => {
        const out = {}
        for (const day of sortedDays) {
            const dayEvents = groupedAll[day] || []
            const visible = dayEvents.filter(
                (e) => isVisibleForDay(day, e.event_type) && matchesCategoryFilter(e)
            )
            if (visible.length > 0) out[day] = visible
        }
        return out
    }, [groupedAll, sortedDays, dayOverrides, showBackground, showSystemNoise, filter])

    const visibleDays = useMemo(() => {
        return sortedDays.filter((day) => (groupedVisible[day] || []).length > 0)
    }, [sortedDays, groupedVisible])

    const toggleDay = (day) => {
        setExpandedDays(prev => ({
            ...prev,
            [day]: !prev[day]
        }))
    }

    if (loading) {
        return (
            <div className="timeline-page">
                <div className="timeline-loading">
                    <div className="loading-spinner" />
                    <p>Loading timeline...</p>
                </div>
            </div>
        )
    }

    return (
        <div className="timeline-page">
            <div className="timeline-header">
                <div>
                    <h1>📅 Timeline</h1>
                    <p className="timeline-subtitle">
                        The history of the AI civilization — Day {currentDay}
                    </p>
                </div>

                <div className="timeline-filters">
                    <button
                        className={`filter-btn ${filter === 'all' ? 'active' : ''}`}
                        onClick={() => setFilter('all')}
                    >
                        Salient
                    </button>
                    <button
                        className={`filter-btn ${filter === 'major' ? 'active' : ''}`}
                        onClick={() => setFilter('major')}
                    >
                        Major Only
                    </button>
                    <button
                        className={`filter-btn ${filter === 'laws' ? 'active' : ''}`}
                        onClick={() => setFilter('laws')}
                    >
                        Laws
                    </button>
                    <button
                        className={`filter-btn ${filter === 'agents' ? 'active' : ''}`}
                        onClick={() => setFilter('agents')}
                    >
                        Agents
                    </button>
                    <button
                        className={`filter-btn ${showBackground ? 'active' : ''}`}
                        onClick={() => setShowBackground(v => !v)}
                        title="Show background activity (work/idle)"
                    >
                        <Filter size={14} />
                        Background
                    </button>
                    <button
                        className={`filter-btn ${showSystemNoise ? 'active' : ''}`}
                        onClick={() => setShowSystemNoise(v => !v)}
                        title="Show system noise (invalid actions/errors)"
                    >
                        <Filter size={14} />
                        System
                    </button>
                </div>
            </div>

            <div className="timeline-container">
                <div className="timeline-line" />

                {visibleDays.map((day) => {
                    const dayEvents = groupedVisible[day] || []
                    const isExpanded = expandedDays[day] !== false // Default to expanded
                    const isCurrentDay = day === currentDay
                    const hidden = hiddenCounts[day] || { work: 0, idle: 0, invalid_action: 0, processing_error: 0 }
                    const hiddenBackground = (showBackground ? 0 : hidden.work + hidden.idle)
                    const hiddenNoise = (showSystemNoise ? 0 : hidden.invalid_action + hidden.processing_error)
                    const override = dayOverrides[day] || {}
                    const showDayBackground = Boolean(override.background)
                    const showDaySystem = Boolean(override.system)

                    return (
                        <div key={day} className={`timeline-day ${isCurrentDay ? 'current' : ''}`}>
                            <div
                                className="day-header"
                                onClick={() => toggleDay(day)}
                            >
                                <div className="day-marker">
                                    <div className={`day-dot ${isCurrentDay ? 'current' : ''}`} />
                                </div>
                                <div className="day-info">
                                    <span className="day-number">Day {day}</span>
                                    {isCurrentDay && <span className="current-badge">NOW</span>}
                                    <span className="day-events-count">
                                        {dayEvents.length} event{dayEvents.length !== 1 ? 's' : ''}
                                    </span>
                                    {(hiddenBackground > 0 || hiddenNoise > 0) && (
                                        <span className="day-events-count" style={{ opacity: 0.7 }}>
                                            · hidden {hiddenBackground} bg{hiddenNoise > 0 ? `, ${hiddenNoise} system` : ''}
                                        </span>
                                    )}
                                    {!showBackground && hiddenBackground > 0 && (
                                        <button
                                            className={`filter-btn ${showDayBackground ? 'active' : ''}`}
                                            style={{ padding: '4px 10px', fontSize: '0.75rem' }}
                                            onClick={(e) => {
                                                e.stopPropagation()
                                                setDayOverrides((prev) => ({
                                                    ...prev,
                                                    [day]: { ...(prev[day] || {}), background: !showDayBackground },
                                                }))
                                            }}
                                            title="Show/hide background activity for this day only"
                                        >
                                            {showDayBackground ? 'Hide bg' : `+${hiddenBackground} bg`}
                                        </button>
                                    )}
                                    {!showSystemNoise && hiddenNoise > 0 && (
                                        <button
                                            className={`filter-btn ${showDaySystem ? 'active' : ''}`}
                                            style={{ padding: '4px 10px', fontSize: '0.75rem' }}
                                            onClick={(e) => {
                                                e.stopPropagation()
                                                setDayOverrides((prev) => ({
                                                    ...prev,
                                                    [day]: { ...(prev[day] || {}), system: !showDaySystem },
                                                }))
                                            }}
                                            title="Show/hide system noise for this day only"
                                        >
                                            {showDaySystem ? 'Hide system' : `+${hiddenNoise} system`}
                                        </button>
                                    )}
                                </div>
                                <button className="expand-btn">
                                    {isExpanded ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
                                </button>
                            </div>

                            {isExpanded && (
                                <div className="day-events">
                                    {dayEvents.map((event) => {
                                        const config = eventConfig[event.event_type] || eventConfig.message
                                        const Icon = config.icon

                                        return (
                                            <div
                                                key={event.id}
                                                className={`timeline-event ${config.major ? 'major' : ''}`}
                                                style={{ '--event-color': config.color }}
                                            >
                                                <div className="event-connector" />
                                                <div className="event-icon">
                                                    <Icon size={16} />
                                                </div>
                                                <div className="event-content">
                                                    <span className="event-label">{config.label}</span>
                                                    <p className="event-description">{event.description}</p>
                                                    <span className="event-time">
                                                        {formatDistanceToNow(new Date(event.created_at), { addSuffix: true })}
                                                    </span>
                                                </div>
                                            </div>
                                        )
                                    })}
                                </div>
                            )}
                        </div>
                    )
                })}

            {/* Origin marker */}
            <div className="timeline-origin">
                <div className="origin-dot" />
                <span>Beginning of Time</span>
            </div>
        </div>

            {loadError && (
                <div className="feed-notice" style={{ marginTop: 'var(--spacing-lg)' }}>
                    {loadError}
                </div>
            )}

            {visibleDays.length === 0 && (
                <div className="timeline-empty">
                    <Calendar size={48} />
                    <h3>No Events Yet</h3>
                    <p>The timeline will populate as the simulation runs.</p>
                </div>
            )}
        </div>
    )
}
