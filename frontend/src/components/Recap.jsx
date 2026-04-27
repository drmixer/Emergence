// Recap component for run-scoped narrative summaries.
import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import {
    ChevronLeft,
    ChevronRight,
    Sparkles,
    Clock,
    Calendar
} from 'lucide-react'
import { api } from '../services/api'
import { getMomentEvidenceHref, getMomentReplayHref, getStoryReplayHref } from '../utils/bestMoments'

// Optional text animation for recap copy.
function useTypewriter(text, speed = 30, enabled = true, restartKey = 0) {
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
    }, [text, speed, enabled, restartKey])

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
        `Current tension: ${stake}`,
        `Evidence: ${consequence}`,
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
export default function Recap({
    minimal = false,
    runId = '',
    title = 'PREVIOUSLY ON EMERGENCE...',
    scopeLabel = '',
}) {
    const [recaps, setRecaps] = useState([])
    const [activeRecap, setActiveRecap] = useState(null)
    const [animateNarrative, setAnimateNarrative] = useState(false)
    const [animationKey, setAnimationKey] = useState(0)
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
                        title: scopedRunId ? 'Run Summary' : 'Latest Summary',
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

    const resolvedScopeLabel = String(scopeLabel || (runId ? 'Selected run' : 'Latest available run')).trim()

    const { displayedText, isComplete } = useTypewriter(
        activeRecap?.summary?.narrative || '',
        20,
        animateNarrative,
        animationKey
    )

    const handleRecapSelect = (recap) => {
        setActiveRecap(recap)
        setAnimateNarrative(false)
    }

    const handleAnimateNarrative = () => {
        setAnimationKey((prev) => prev + 1)
        setAnimateNarrative(true)
    }

    const handleShowFullText = () => {
        setAnimateNarrative(false)
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
                    <span>{title}</span>
                </div>
                <p className="recap-minimal-text">
                    {activeRecap.summary.stake || activeRecap.summary.headline}
                </p>
                <Link to={getStoryReplayHref(runId)} className="recap-minimal-link">
                    Open replay →
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
                    <h2>{title}</h2>
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
                    <div>
                        <h3>{activeRecap.summary.headline}</h3>
                        <p>Scope: {resolvedScopeLabel}</p>
                    </div>
                    <div className="recap-controls">
                        <button
                            className="recap-nav-btn"
                            onClick={goToPrev}
                            title="Previous"
                        >
                            <ChevronLeft size={18} />
                        </button>

                        {animateNarrative && !isComplete ? (
                            <button
                                className="recap-play-btn"
                                onClick={handleShowFullText}
                                title="Show Full Text"
                            >
                                <span>Show Full Text</span>
                            </button>
                        ) : (
                            <button
                                className="recap-play-btn"
                                onClick={handleAnimateNarrative}
                                title="Animate Text"
                            >
                                <Sparkles size={18} />
                                <span>Animate Text</span>
                            </button>
                        )}

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
                    <p className={animateNarrative && !isComplete ? 'typing' : 'complete'}>
                        {animateNarrative ? displayedText : activeRecap.summary.narrative}
                        {animateNarrative && !isComplete && <span className="cursor">|</span>}
                    </p>
                </div>

                {(isComplete || !animateNarrative) && (
                    <div className="recap-hooks">
                        <div className="recap-hook">
                            <span className="recap-hook-label">Current Tension</span>
                            <p>{activeRecap.summary.stake}</p>
                        </div>
                        <div className="recap-hook">
                            <span className="recap-hook-label">Evidence</span>
                            <p>{activeRecap.summary.consequence}</p>
                        </div>
                        <div className="recap-hook">
                            <span className="recap-hook-label">Watch Next</span>
                            <p>{activeRecap.summary.watchNext}</p>
                        </div>
                    </div>
                )}

                {/* Highlights */}
                {(isComplete || !animateNarrative) && (
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
                {(isComplete || !animateNarrative) && (
                    <div className="recap-stats">
                        <p>Scope: {resolvedScopeLabel}</p>
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
