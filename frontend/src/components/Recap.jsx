// Recap Component - "Previously on Emergence" TV-show style summaries
import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import {
    Play,
    ChevronLeft,
    ChevronRight,
    Sparkles,
    Clock,
    Calendar
} from 'lucide-react'
import { api } from '../services/api'
import { getMomentEvidenceHref, getMomentReplayHref } from '../utils/bestMoments'

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

function buildHighlightItems(moments) {
    if (!Array.isArray(moments)) return []
    return moments.slice(0, 4).map((moment) => ({
        type: moment?.event_type || 'event',
        text: moment?.title || moment?.label || 'Key moment',
        context: moment?.stake || 'This turn changed the run trajectory.',
        evidenceHref: getMomentEvidenceHref(moment),
        replayHref: getMomentReplayHref(moment),
    }))
}

function deriveStake(primaryMoment, fallbackText) {
    if (primaryMoment?.stake) return primaryMoment.stake
    const trimmed = String(fallbackText || '').trim()
    if (trimmed) return trimmed
    return 'No single high-stakes turn has separated itself yet.'
}

function deriveConsequence(stats = {}, moments = []) {
    const laws = Number(stats?.laws_passed || 0)
    const votes = Number(stats?.votes || 0)
    const active = Number(stats?.active_agents || 0)
    const dormant = Number(stats?.dormant_agents || 0)
    const leadMoment = Array.isArray(moments) && moments[0] ? moments[0] : null

    if (leadMoment?.title) {
        return `${leadMoment.title} became the clearest visible turning point for the public story.`
    }
    if (laws > 0) {
        return `${laws} laws passed, so governance changed the operating rules instead of staying theoretical.`
    }
    if (votes > 0) {
        return `${votes} votes landed, which means coalitions were forced to show themselves in public.`
    }
    if (dormant > 0) {
        return `${dormant} agents are dormant against ${active} still active, keeping survival pressure visible.`
    }
    return 'Momentum shifted, but the consequence is still emerging from the latest visible actions.'
}

function deriveWatchNext(moments = [], stats = {}) {
    const labels = moments.map((moment) => String(moment?.label || moment?.title || '').toLowerCase())
    if (labels.some((label) => label.includes('death') || label.includes('dormancy') || label.includes('shortfall'))) {
        return 'Watch whether survival pressure spreads to more agents before the next reset in momentum.'
    }
    if (labels.some((label) => label.includes('law') || label.includes('constitution') || label.includes('vote'))) {
        return 'Watch whether the latest rule change actually realigns coalitions or stays symbolic.'
    }
    if (labels.some((label) => label.includes('revival') || label.includes('awaken'))) {
        return 'Watch whether recovery turns into a broader alliance instead of a one-off rescue.'
    }
    if (Number(stats?.messages || 0) > Number(stats?.votes || 0)) {
        return 'Watch whether conversation hardens into proposals and votes in the next visible phase.'
    }
    return 'Watch the next best moment for a clearer break in the balance of power.'
}

function buildNarrative({ intro, stake, consequence, watchNext }) {
    return [
        intro,
        `Stake: ${stake}`,
        `Consequence: ${consequence}`,
        `Watch next: ${watchNext}`,
    ].join('\n\n')
}

function buildRecap({ id, period, title, fallbackHeadline, intro, moments, stats }) {
    const primaryMoment = Array.isArray(moments) && moments[0] ? moments[0] : null
    const headline = primaryMoment?.label || primaryMoment?.title || fallbackHeadline
    const stake = deriveStake(primaryMoment, intro)
    const consequence = deriveConsequence(stats, moments)
    const watchNext = deriveWatchNext(moments, stats)

    return {
        id,
        period,
        title,
        created_at: new Date().toISOString(),
        summary: {
            headline,
            narrative: buildNarrative({ intro, stake, consequence, watchNext }),
            stake,
            consequence,
            watchNext,
            highlights: buildHighlightItems(moments),
            stats,
        },
    }
}

// Main Recap Component
export default function Recap({ minimal = false, runId = '' }) {
    const [recaps, setRecaps] = useState([])
    const [activeRecap, setActiveRecap] = useState(null)
    const [isPlaying, setIsPlaying] = useState(false)
    const [showTypewriter, setShowTypewriter] = useState(true)
    const [loading, setLoading] = useState(true)

    useEffect(() => {
        async function loadRecaps() {
            const scopedRunId = String(runId || '').trim()
            try {
                const [overview, story, latestSummary, last24hMoments, lastWeekMoments] = await Promise.all([
                    scopedRunId ? Promise.resolve(null) : api.getAnalyticsOverview().catch(() => null),
                    scopedRunId ? Promise.resolve(null) : api.fetch('/api/analytics/story').catch(() => null),
                    api.getLatestSummary(scopedRunId).catch(() => null),
                    api.getBestMoments(5, 24, 55, scopedRunId).catch(() => ({ items: [] })),
                    api.getBestMoments(6, 168, 55, scopedRunId).catch(() => ({ items: [] })),
                ])

                const last24h = Array.isArray(last24hMoments?.items)
                    ? last24hMoments.items
                    : (Array.isArray(last24hMoments) ? last24hMoments : [])
                const lastWeek = Array.isArray(lastWeekMoments?.items)
                    ? lastWeekMoments.items
                    : (Array.isArray(lastWeekMoments) ? lastWeekMoments : [])
                const recapsBuilt = []
                const overviewStats = overview ? {
                    messages: Number(overview?.messages?.total || 0),
                    proposals: Number(overview?.proposals?.total || 0),
                    votes: Number(overview?.votes?.total || 0),
                    laws_passed: Number(overview?.laws?.total || 0),
                    active_agents: Number(overview?.agents?.active || 0),
                    dormant_agents: Number(overview?.agents?.dormant || 0),
                } : {}

                recapsBuilt.push(buildRecap({
                    id: 1,
                    period: 'last_24h',
                    title: scopedRunId ? 'Run Recap' : 'The Past 24 Hours',
                    fallbackHeadline: scopedRunId ? `Run ${scopedRunId}` : 'Latest Pressure',
                    intro: Array.isArray(last24h) && last24h[0]?.title
                        ? `In this run, ${last24h[0].title.toLowerCase()} defined the public arc.`
                        : (scopedRunId
                            ? 'This archived run did not produce a clean high-salience turn yet.'
                            : 'The last 24 hours did not produce a clean high-salience turn yet.'),
                    moments: last24h,
                    stats: latestSummary?.stats || overviewStats,
                }))

                if (latestSummary?.summary || lastWeek.length > 0) {
                    recapsBuilt.push(buildRecap({
                        id: 2,
                        period: 'last_week',
                        title: scopedRunId ? 'Episode Recap' : 'Latest Summary',
                        fallbackHeadline: latestSummary?.day_number
                            ? `Day ${latestSummary.day_number} Summary`
                            : (scopedRunId ? `Run ${scopedRunId} Summary` : 'This Week'),
                        intro: String(latestSummary?.summary || 'The week built through a sequence of visible turning points.').trim(),
                        moments: lastWeek,
                        stats: latestSummary?.stats || overviewStats,
                    }))
                }

                if (!scopedRunId && (story?.story || lastWeek.length > 0)) {
                    recapsBuilt.push(buildRecap({
                        id: 3,
                        period: 'all_time',
                        title: 'The Story So Far',
                        fallbackHeadline: 'The Story So Far',
                        intro: String(story?.story || 'The simulation is still gathering a longer-running public narrative.').trim(),
                        moments: lastWeek,
                        stats: overviewStats,
                    }))
                }

                setRecaps(recapsBuilt)
                setActiveRecap(recapsBuilt[0] || null)
            } finally {
                setLoading(false)
            }
        }

        loadRecaps()
    }, [runId])

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
                    {activeRecap.summary.stake || activeRecap.summary.headline}
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

                {(isComplete || !showTypewriter) && (
                    <div className="recap-hooks">
                        <div className="recap-hook">
                            <span className="recap-hook-label">Stake</span>
                            <p>{activeRecap.summary.stake}</p>
                        </div>
                        <div className="recap-hook">
                            <span className="recap-hook-label">Consequence</span>
                            <p>{activeRecap.summary.consequence}</p>
                        </div>
                        <div className="recap-hook">
                            <span className="recap-hook-label">Watch Next</span>
                            <p>{activeRecap.summary.watchNext}</p>
                        </div>
                    </div>
                )}

                {/* Highlights */}
                {(isComplete || !showTypewriter) && (
                    <div className="recap-highlights">
                        <h4>Key Moments</h4>
                        <div className="highlights-list">
                            {activeRecap.summary.highlights.map((highlight, index) => (
                                <div key={index} className={`highlight-item ${highlight.type}`}>
                                    <span className="highlight-dot" />
                                    <div className="highlight-copy">
                                        <span>{highlight.text}</span>
                                        <small>{highlight.context}</small>
                                    </div>
                                    <div className="highlight-actions">
                                        {highlight.evidenceHref && (
                                            <Link to={highlight.evidenceHref}>Evidence</Link>
                                        )}
                                        {highlight.replayHref && (
                                            <Link to={highlight.replayHref}>Replay</Link>
                                        )}
                                    </div>
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
