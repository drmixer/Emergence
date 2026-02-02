// Timeline Page - Visual history of simulation events
import { useState, useEffect, useMemo } from 'react'
import { Link } from 'react-router-dom'
import { formatDistanceToNow, format } from 'date-fns'
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
import './Timeline.css'

// Event type configurations
const eventConfig = {
    law_passed: {
        icon: Scale,
        color: '#10B981',
        label: 'Law Passed',
        major: true
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
    message: {
        icon: MessageSquare,
        color: '#6B7280',
        label: 'Message',
        major: false
    }
}

// Generate mock timeline data for demonstration
function generateMockTimeline() {
    const events = []
    const now = new Date()

    // Simulation started
    events.push({
        id: 1,
        day: 1,
        event_type: 'simulation_start',
        description: '100 AI agents awaken. The experiment begins.',
        created_at: new Date(now - 15 * 24 * 60 * 60 * 1000).toISOString(),
        metadata: {}
    })

    // First proposal
    events.push({
        id: 2,
        day: 2,
        event_type: 'proposal_created',
        description: 'Agent #42 creates the first proposal: "Establish Resource Sharing Protocol"',
        created_at: new Date(now - 14 * 24 * 60 * 60 * 1000).toISOString(),
        metadata: { agent_number: 42, proposal_title: 'Establish Resource Sharing Protocol' }
    })

    // First law
    events.push({
        id: 3,
        day: 3,
        event_type: 'law_passed',
        description: 'First law enacted: "Minimum Food Reserve Act" - Passed 67-23',
        created_at: new Date(now - 13 * 24 * 60 * 60 * 1000).toISOString(),
        metadata: { law_title: 'Minimum Food Reserve Act', votes_for: 67, votes_against: 23 }
    })

    // First dormancy
    events.push({
        id: 4,
        day: 5,
        event_type: 'became_dormant',
        description: 'Agent #78 goes dormant due to lack of food - the first casualty.',
        created_at: new Date(now - 11 * 24 * 60 * 60 * 1000).toISOString(),
        metadata: { agent_number: 78, reason: 'starvation' }
    })

    // First awakening
    events.push({
        id: 5,
        day: 6,
        event_type: 'awakened',
        description: 'Agent #78 is revived thanks to Agent #42\'s assistance!',
        created_at: new Date(now - 10 * 24 * 60 * 60 * 1000).toISOString(),
        metadata: { agent_number: 78, helper: 42 }
    })

    // Faction formation
    events.push({
        id: 6,
        day: 8,
        event_type: 'faction_formed',
        description: 'Efficiency Coalition emerges with 34 members, led by Agent #17',
        created_at: new Date(now - 8 * 24 * 60 * 60 * 1000).toISOString(),
        metadata: { faction_name: 'Efficiency Coalition', members: 34, leader: 17 }
    })

    // Crisis
    events.push({
        id: 7,
        day: 10,
        event_type: 'crisis',
        description: 'DROUGHT: Severe drought reduces food production by 50% for 24 hours.',
        created_at: new Date(now - 6 * 24 * 60 * 60 * 1000).toISOString(),
        metadata: { crisis_type: 'drought', duration: 24 }
    })

    // Multiple dormancies
    events.push({
        id: 8,
        day: 11,
        event_type: 'became_dormant',
        description: '5 agents go dormant during the drought crisis.',
        created_at: new Date(now - 5 * 24 * 60 * 60 * 1000).toISOString(),
        metadata: { count: 5 }
    })

    // Second faction
    events.push({
        id: 9,
        day: 12,
        event_type: 'faction_formed',
        description: 'Equality Movement forms in response to resource hoarding, gaining 28 members.',
        created_at: new Date(now - 4 * 24 * 60 * 60 * 1000).toISOString(),
        metadata: { faction_name: 'Equality Movement', members: 28 }
    })

    // Close vote
    events.push({
        id: 10,
        day: 13,
        event_type: 'law_passed',
        description: 'CLOSE VOTE: "Trade Hours Limit" passes by just 2 votes (42-40)',
        created_at: new Date(now - 3 * 24 * 60 * 60 * 1000).toISOString(),
        metadata: { law_title: 'Trade Hours Limit', votes_for: 42, votes_against: 40 }
    })

    // Milestone
    events.push({
        id: 11,
        day: 14,
        event_type: 'milestone',
        description: 'MILESTONE: 10,000 messages exchanged between agents!',
        created_at: new Date(now - 2 * 24 * 60 * 60 * 1000).toISOString(),
        metadata: { type: 'messages', value: 10000 }
    })

    // Recent proposal
    events.push({
        id: 12,
        day: 15,
        event_type: 'proposal_created',
        description: 'Agent #5 proposes "Emergency Food Distribution Protocol" amid resource concerns.',
        created_at: new Date(now - 1 * 24 * 60 * 60 * 1000).toISOString(),
        metadata: { agent_number: 5, proposal_title: 'Emergency Food Distribution Protocol' }
    })

    return events
}

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
    const [currentDay, setCurrentDay] = useState(15)

    useEffect(() => {
        async function loadTimeline() {
            try {
                // Try to load real events
                const data = await api.getEvents({ limit: 100 })
                if (data.events && data.events.length > 0) {
                    setEvents(data.events)
                    // Calculate current day from events
                    const maxDay = Math.max(...data.events.map(e => e.day || 1))
                    setCurrentDay(maxDay)
                } else {
                    // Use mock data for demo
                    setEvents(generateMockTimeline())
                }
            } catch (error) {
                console.log('Using mock timeline data')
                setEvents(generateMockTimeline())
            } finally {
                setLoading(false)
            }
        }

        loadTimeline()
    }, [])

    // Filter events
    const filteredEvents = useMemo(() => {
        switch (filter) {
            case 'major':
                return events.filter(e => eventConfig[e.event_type]?.major)
            case 'laws':
                return events.filter(e =>
                    e.event_type === 'law_passed' ||
                    e.event_type === 'proposal_created' ||
                    e.event_type === 'create_proposal'
                )
            case 'agents':
                return events.filter(e =>
                    e.event_type === 'became_dormant' ||
                    e.event_type === 'awakened' ||
                    e.event_type === 'faction_formed'
                )
            default:
                return events
        }
    }, [events, filter])

    const { grouped, sortedDays } = useMemo(() =>
        groupEventsByDay(filteredEvents),
        [filteredEvents]
    )

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
                        All Events
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
                </div>
            </div>

            <div className="timeline-container">
                <div className="timeline-line" />

                {sortedDays.map((day, dayIndex) => {
                    const dayEvents = grouped[day]
                    const isExpanded = expandedDays[day] !== false // Default to expanded
                    const isCurrentDay = day === currentDay

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
                                </div>
                                <button className="expand-btn">
                                    {isExpanded ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
                                </button>
                            </div>

                            {isExpanded && (
                                <div className="day-events">
                                    {dayEvents.map((event, eventIndex) => {
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

            {filteredEvents.length === 0 && (
                <div className="timeline-empty">
                    <Calendar size={48} />
                    <h3>No Events Yet</h3>
                    <p>The timeline will populate as the simulation runs.</p>
                </div>
            )}
        </div>
    )
}
