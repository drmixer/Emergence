// Recap Component - "Previously on Emergence" TV-show style summaries
import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import {
    Play,
    Pause,
    ChevronLeft,
    ChevronRight,
    Sparkles,
    Volume2,
    VolumeX,
    Clock,
    Calendar
} from 'lucide-react'
import { api } from '../services/api'

// Typewriter effect hook
function useTypewriter(text, speed = 30, enabled = true) {
    const [displayedText, setDisplayedText] = useState('')
    const [isComplete, setIsComplete] = useState(false)

    useEffect(() => {
        if (!enabled) {
            setDisplayedText(text)
            setIsComplete(true)
            return
        }

        setDisplayedText('')
        setIsComplete(false)

        let index = 0
        const timer = setInterval(() => {
            if (index < text.length) {
                setDisplayedText(text.slice(0, index + 1))
                index++
            } else {
                setIsComplete(true)
                clearInterval(timer)
            }
        }, speed)

        return () => clearInterval(timer)
    }, [text, speed, enabled])

    return { displayedText, isComplete }
}

// Single Recap Card
function RecapCard({ recap, isActive, onSelect }) {
    const periodLabels = {
        'last_24h': '24 Hours',
        'last_week': 'This Week',
        'all_time': 'All Time'
    }

    return (
        <div
            className={`recap-card ${isActive ? 'active' : ''}`}
            onClick={() => onSelect(recap)}
        >
            <div className="recap-card-icon">
                {recap.period === 'last_24h' && <Clock size={20} />}
                {recap.period === 'last_week' && <Calendar size={20} />}
                {recap.period === 'all_time' && <Sparkles size={20} />}
            </div>
            <span className="recap-card-label">{periodLabels[recap.period]}</span>
            <span className="recap-card-title">{recap.summary.headline}</span>
        </div>
    )
}

// Main Recap Component
export default function Recap({ minimal = false }) {
    const [recaps, setRecaps] = useState([])
    const [activeRecap, setActiveRecap] = useState(null)
    const [isPlaying, setIsPlaying] = useState(false)
    const [showTypewriter, setShowTypewriter] = useState(true)
    const [loading, setLoading] = useState(true)

    useEffect(() => {
        async function loadRecaps() {
            try {
                const [overview, story, latestSummary, dramatic, featured] = await Promise.all([
                    api.getAnalyticsOverview().catch(() => null),
                    api.fetch('/api/analytics/story').catch(() => null),
                    api.fetch('/api/analytics/summaries/latest').catch(() => null),
                    api.fetch('/api/analytics/dramatic?hours=24&limit=10').catch(() => []),
                    api.fetch('/api/analytics/featured?limit=6').catch(() => []),
                ])

                const recapsBuilt = []

                const featuredHighlights = Array.isArray(featured)
                    ? featured.slice(0, 5).map(e => ({ type: e.event_type || 'event', text: e.title || e.description || 'Event' }))
                    : []

                const dramaticLines = Array.isArray(dramatic)
                    ? dramatic
                        .filter(d => d?.title || d?.description)
                        .slice(0, 8)
                        .map(d => `- ${d.title || d.description}`)
                    : []

                recapsBuilt.push({
                    id: 1,
                    period: 'last_24h',
                    title: 'The Past 24 Hours',
                    created_at: new Date().toISOString(),
                    summary: {
                        headline: dramaticLines.length > 0 ? 'The Past 24 Hours' : 'No dramatic events yet',
                        narrative: dramaticLines.length > 0 ? dramaticLines.join('\n') : 'The simulation is still warming up.',
                        highlights: featuredHighlights,
                        stats: overview?.messages ? {
                            messages: overview.messages.total,
                            proposals: overview.proposals?.total,
                            votes: overview.votes?.total,
                            laws_passed: overview.laws?.total,
                        } : {},
                    }
                })

                if (latestSummary?.summary) {
                    recapsBuilt.push({
                        id: 2,
                        period: 'last_week',
                        title: 'Latest Summary',
                        created_at: latestSummary.created_at || new Date().toISOString(),
                        summary: {
                            headline: latestSummary.day_number ? `Day ${latestSummary.day_number} Summary` : 'Latest Summary',
                            narrative: latestSummary.summary,
                            highlights: featuredHighlights,
                            stats: latestSummary.stats || {},
                        }
                    })
                }

                if (story?.story) {
                    recapsBuilt.push({
                        id: 3,
                        period: 'all_time',
                        title: 'The Story So Far',
                        created_at: new Date().toISOString(),
                        summary: {
                            headline: 'The Story So Far',
                            narrative: story.story,
                            highlights: featuredHighlights,
                            stats: {},
                        }
                    })
                }

                setRecaps(recapsBuilt)
                setActiveRecap(recapsBuilt[0] || null)
            } finally {
                setLoading(false)
            }
        }

        loadRecaps()
    }, [])

    const { displayedText, isComplete } = useTypewriter(
        activeRecap?.summary?.narrative || '',
        20,
        showTypewriter && isPlaying
    )

    const handleRecapSelect = (recap) => {
        setActiveRecap(recap)
        setIsPlaying(false)
        setShowTypewriter(true)
    }

    const handlePlay = () => {
        setIsPlaying(true)
        setShowTypewriter(true)
    }

    const handleSkip = () => {
        setShowTypewriter(false)
        setIsPlaying(false)
    }

    const goToNext = () => {
        const currentIndex = recaps.findIndex(r => r.id === activeRecap.id)
        const nextIndex = (currentIndex + 1) % recaps.length
        handleRecapSelect(recaps[nextIndex])
    }

    const goToPrev = () => {
        const currentIndex = recaps.findIndex(r => r.id === activeRecap.id)
        const prevIndex = (currentIndex - 1 + recaps.length) % recaps.length
        handleRecapSelect(recaps[prevIndex])
    }

    if (loading) {
        return (
            <div className={`recap-container ${minimal ? 'minimal' : ''}`}>
                <div className="recap-loading">
                    <div className="loading-spinner" />
                    <p>Generating recap...</p>
                </div>
            </div>
        )
    }

    if (!activeRecap) {
        return null
    }

    // Minimal version for dashboard
    if (minimal) {
        return (
            <div className="recap-container minimal">
                <div className="recap-minimal-header">
                    <Sparkles size={16} />
                    <span>Previously on Emergence...</span>
                </div>
                <p className="recap-minimal-text">
                    {activeRecap.summary.headline}
                </p>
                <Link to="/highlights" className="recap-minimal-link">
                    Read full recap →
                </Link>
            </div>
        )
    }

    return (
        <div className="recap-container">
            {/* Header */}
            <div className="recap-header">
                <div className="recap-header-text">
                    <span className="recap-eyebrow">━━━━━━━━━━━━━━━━━━━━━</span>
                    <h2>PREVIOUSLY ON EMERGENCE...</h2>
                    <span className="recap-eyebrow">━━━━━━━━━━━━━━━━━━━━━</span>
                </div>
            </div>

            {/* Period Selector */}
            <div className="recap-periods">
                {recaps.map(recap => (
                    <RecapCard
                        key={recap.id}
                        recap={recap}
                        isActive={activeRecap.id === recap.id}
                        onSelect={handleRecapSelect}
                    />
                ))}
            </div>

            {/* Main Content */}
            <div className="recap-content">
                <div className="recap-narrative-header">
                    <h3>{activeRecap.summary.headline}</h3>
                    <div className="recap-controls">
                        <button
                            className="recap-nav-btn"
                            onClick={goToPrev}
                            title="Previous"
                        >
                            <ChevronLeft size={18} />
                        </button>

                        {!isPlaying && !isComplete ? (
                            <button
                                className="recap-play-btn"
                                onClick={handlePlay}
                                title="Play"
                            >
                                <Play size={18} />
                                <span>Play</span>
                            </button>
                        ) : isPlaying && !isComplete ? (
                            <button
                                className="recap-skip-btn"
                                onClick={handleSkip}
                                title="Skip"
                            >
                                <span>Skip</span>
                            </button>
                        ) : null}

                        <button
                            className="recap-nav-btn"
                            onClick={goToNext}
                            title="Next"
                        >
                            <ChevronRight size={18} />
                        </button>
                    </div>
                </div>

                <div className="recap-narrative">
                    {isPlaying || showTypewriter === false ? (
                        <p className={isComplete ? 'complete' : 'typing'}>
                            {showTypewriter ? displayedText : activeRecap.summary.narrative}
                            {!isComplete && showTypewriter && <span className="cursor">|</span>}
                        </p>
                    ) : (
                        <div className="recap-play-prompt">
                            <Play size={32} />
                            <p>Click Play to experience the recap</p>
                        </div>
                    )}
                </div>

                {/* Highlights */}
                {(isComplete || !showTypewriter) && (
                    <div className="recap-highlights">
                        <h4>Key Moments</h4>
                        <div className="highlights-list">
                            {activeRecap.summary.highlights.map((highlight, index) => (
                                <div key={index} className={`highlight-item ${highlight.type}`}>
                                    <span className="highlight-dot" />
                                    <span>{highlight.text}</span>
                                </div>
                            ))}
                        </div>
                    </div>
                )}

                {/* Stats */}
                {(isComplete || !showTypewriter) && (
                    <div className="recap-stats">
                        {Object.entries(activeRecap.summary.stats).map(([key, value]) => (
                            <div key={key} className="stat-item">
                                <span className="stat-value">
                                    {typeof value === 'number' ? value.toLocaleString() : value}
                                </span>
                                <span className="stat-label">
                                    {key.replace(/_/g, ' ')}
                                </span>
                            </div>
                        ))}
                    </div>
                )}
            </div>
        </div>
    )
}
