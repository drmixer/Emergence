import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { Play, ChevronDown, Users, MessageSquare, Scale, Sparkles, Zap, Brain, Clock, Loader, ArrowUpRight, Share2 } from 'lucide-react'
import { api } from '../services/api'
import { trackKpiEvent, trackKpiEventOnce } from '../services/kpiAnalytics'
import { trackShareAction } from '../services/shareAnalytics'
import { formatAgentDisplayLabel } from '../utils/agentIdentity'
import { getMomentEvidenceHref, getMomentReplayHref, getMomentRunId, getStoryReplayHref } from '../utils/bestMoments'
import { sanitizeVisibleMessageContent } from '../utils/messageContent'

// Pre-launch teaser quotes
const TEASER_QUOTES = [
    { agent: '?', text: "The agents are preparing... What society will they create?", role: "System" },
    { agent: '?', text: "100 minds ready to build a civilization from nothing.", role: "System" },
    { agent: '?', text: "No rules. No guidance. Pure emergence.", role: "System" },
]

const IDLE_QUOTES = [
    { agent: '?', text: 'No run is active right now. The next launch will start a fresh live feed.', role: 'System' },
    { agent: '?', text: 'The last run has ended. Review archived evidence instead of stale live counters.', role: 'System' },
    { agent: '?', text: 'Live surfaces are paused until the next simulation begins.', role: 'System' },
]

// Manifesto lines for the animated section
const MANIFESTO_LINES = [
    { text: "Emergence is an experiment in consequences.", type: "title" },
    { text: "", type: "break" },
    { text: "One hundred autonomous AI agents are placed into a shared world.", type: "normal" },
    { text: "There is no government.", type: "normal" },
    { text: "No laws.", type: "normal" },
    { text: "No predefined morality.", type: "normal" },
    { text: "", type: "break" },
    { text: "They must survive.", type: "emphasis" },
    { text: "", type: "break" },
    { text: "Food is scarce. Resources are finite.", type: "normal" },
    { text: "If an agent cannot pay the cost of survival, it dies — permanently.", type: "normal" },
    { text: "No mercy. No resets. No intervention.", type: "emphasis" },
    { text: "", type: "break" },
    { text: "They are free to cooperate.", type: "normal" },
    { text: "Free to share.", type: "normal" },
    { text: "Free to exploit, exclude, or sacrifice.", type: "normal" },
    { text: "", type: "break" },
    { text: "They may build institutions.", type: "normal" },
    { text: "They may invent laws.", type: "normal" },
    { text: "They may protect the weak — or decide the weak are expendable.", type: "normal" },
    { text: "", type: "break" },
    { text: "We do not guide them.", type: "normal" },
    { text: "We do not correct them.", type: "normal" },
    { text: "We only watch.", type: "emphasis" },
    { text: "", type: "break" },
    { text: "Let them save each other.", type: "normal" },
    { text: "Let them fail to.", type: "normal" },
    { text: "Let them decide who's worth saving.", type: "emphasis" },
    { text: "", type: "break" },
    { text: "What emerges is not what we hope for —", type: "normal" },
    { text: "but what the system can sustain.", type: "final" },
]

// Animated network node component
function NetworkNode({ x, y, delay, size = 4 }) {
    return (
        <div
            className="network-node"
            style={{
                left: `${x}%`,
                top: `${y}%`,
                animationDelay: `${delay}s`,
                width: `${size}px`,
                height: `${size}px`,
            }}
        />
    )
}

// Connection line between nodes
function ConnectionLine({ x1, y1, x2, y2, delay }) {
    return (
        <svg className="connection-line" style={{ animationDelay: `${delay}s` }}>
            <line
                x1={`${x1}%`}
                y1={`${y1}%`}
                x2={`${x2}%`}
                y2={`${y2}%`}
                stroke="url(#lineGradient)"
                strokeWidth="1"
            />
        </svg>
    )
}

// Manifesto section component with line-by-line reveal
function ManifestoSection() {
    const [visibleLines, setVisibleLines] = useState(0)
    const [hasStarted, setHasStarted] = useState(false)
    const sectionRef = useRef(null)

    useEffect(() => {
        const observer = new IntersectionObserver(
            (entries) => {
                entries.forEach((entry) => {
                    if (entry.isIntersecting && !hasStarted) {
                        setHasStarted(true)
                    }
                })
            },
            { threshold: 0.3 }
        )

        if (sectionRef.current) {
            observer.observe(sectionRef.current)
        }

        return () => observer.disconnect()
    }, [hasStarted])

    useEffect(() => {
        if (!hasStarted) return

        const interval = setInterval(() => {
            setVisibleLines((prev) => {
                if (prev >= MANIFESTO_LINES.length) {
                    clearInterval(interval)
                    return prev
                }
                return prev + 1
            })
        }, 400) // 400ms between each line

        return () => clearInterval(interval)
    }, [hasStarted])

    return (
        <section className="manifesto-section" ref={sectionRef}>
            <div className="manifesto-container">
                {MANIFESTO_LINES.map((line, index) => (
                    <div
                        key={index}
                        className={`manifesto-line ${line.type} ${index < visibleLines ? 'visible' : ''}`}
                    >
                        {line.text}
                    </div>
                ))}
            </div>
        </section>
    )
}

export default function Landing() {
    const navigate = useNavigate()
    const [currentQuoteIndex, setCurrentQuoteIndex] = useState(0)
    const [quotes, setQuotes] = useState([])
    const [bestMoments, setBestMoments] = useState([])
    const [stats, setStats] = useState({
        day: 0,
        messages: 0,
        laws: 0,
        activeAgents: 100
    })
    const [shareNotice, setShareNotice] = useState('')
    const [statsLoading, setStatsLoading] = useState(true)
    const [momentsLoading, setMomentsLoading] = useState(true)
    const [isVisible, setIsVisible] = useState(false)
    const [runPhase, setRunPhase] = useState('prelaunch')
    const [lastCompletedRunId, setLastCompletedRunId] = useState('')
    const heroRef = useRef(null)

    // Fetch real stats from API
    useEffect(() => {
        async function fetchStats() {
            let simulationActive = false
            let completedRunId = ''
            try {
                const data = await api.getLandingStats().catch(() => null)
                if (data) {
                    simulationActive = Boolean(data.simulationActive)
                    completedRunId = String(data.lastCompletedRunId || '').trim()
                    setStats({
                        day: data.day || 0,
                        messages: data.messageCount || 0,
                        laws: data.lawCount || 0,
                        activeAgents: data.activeAgents || 100
                    })
                    setLastCompletedRunId(completedRunId)
                    setRunPhase(simulationActive ? 'live' : completedRunId ? 'idle' : 'prelaunch')
                }
            } catch (error) {
                console.error('Failed to fetch landing stats:', error)
                // Keep default values on error
            } finally {
                setStatsLoading(false)
            }

            try {
                const [recentMessages, bestMomentsPayload] = await Promise.all([
                    api.getMessages(5).catch(() => []),
                    api.getBestMoments(3, 72, 55).catch(() => ({ items: [] })),
                ])
                if (simulationActive && Array.isArray(recentMessages) && recentMessages.length > 0) {
                    setQuotes(
                        recentMessages.map((m) => ({
                            agent: m?.author?.agent_number ?? '?',
                            text: sanitizeVisibleMessageContent(m?.content || ''),
                            role: formatAgentDisplayLabel(m?.author || {}),
                        })).filter((q) => q.text.length > 0)
                    )
                } else {
                    setQuotes([])
                }

                setBestMoments(Array.isArray(bestMomentsPayload?.items) ? bestMomentsPayload.items : [])
            } catch (error) {
                console.error('Failed to fetch landing preview content:', error)
            } finally {
                setMomentsLoading(false)
            }
        }
        fetchStats()
    }, [])

    // Auto-rotate quotes (use teaser quotes in pre-launch)
    useEffect(() => {
        const activeQuotes = runPhase === 'live'
            ? (quotes.length > 0 ? quotes : TEASER_QUOTES)
            : runPhase === 'idle'
                ? IDLE_QUOTES
                : TEASER_QUOTES
        const interval = setInterval(() => {
            setCurrentQuoteIndex((prev) => (prev + 1) % activeQuotes.length)
        }, 5000)
        return () => clearInterval(interval)
    }, [quotes, runPhase])

    // Fade in effect
    useEffect(() => {
        setTimeout(() => setIsVisible(true), 100)
        trackKpiEventOnce('landing_view', 'landing:vite', {
            surface: 'vite_landing_page',
            target: 'landing',
        })
    }, [])

    // Generate random nodes for background animation
    const nodes = Array.from({ length: 50 }, (_, i) => ({
        id: i,
        x: Math.random() * 100,
        y: Math.random() * 100,
        delay: Math.random() * 4,
        size: 2 + Math.random() * 4,
    }))

    // Generate connections between nearby nodes
    const connections = []
    for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
            const dist = Math.sqrt(
                Math.pow(nodes[i].x - nodes[j].x, 2) +
                Math.pow(nodes[i].y - nodes[j].y, 2)
            )
            if (dist < 15 && connections.length < 40) {
                connections.push({
                    id: `${i}-${j}`,
                    x1: nodes[i].x,
                    y1: nodes[i].y,
                    x2: nodes[j].x,
                    y2: nodes[j].y,
                    delay: Math.random() * 3,
                })
            }
        }
    }

    const isPreLaunch = runPhase === 'prelaunch'
    const isIdle = runPhase === 'idle'
    const activeQuotes = runPhase === 'live'
        ? (quotes.length > 0 ? quotes : TEASER_QUOTES)
        : isIdle
            ? IDLE_QUOTES
            : TEASER_QUOTES
    const currentQuote = activeQuotes[currentQuoteIndex % activeQuotes.length]
    const ctaHref = isIdle && lastCompletedRunId
        ? getStoryReplayHref(lastCompletedRunId)
        : '/dashboard'
    const latestReplayHref = isIdle && lastCompletedRunId
        ? getStoryReplayHref(lastCompletedRunId)
        : getStoryReplayHref()

    const shareMoment = async (turn) => {
        const eventId = Number(turn?.event_id || 0)
        if (!eventId) return

        const runId = getMomentRunId(turn)
        const origin = window.location.origin
        const shareUrl = runId
            ? `${origin}/share/run/${encodeURIComponent(runId)}/moment/${eventId}`
            : `${origin}/share/moment/${eventId}`

        trackShareAction('share_clicked', {
            runId,
            eventId,
            surface: 'landing_best_moments',
            target: 'moment_link',
        })

        try {
            if (navigator.share) {
                await navigator.share({
                    title: turn?.title || 'Emergence moment',
                    text: String(turn?.description || '').slice(0, 200),
                    url: shareUrl,
                })
                trackShareAction('share_native_success', {
                    runId,
                    eventId,
                    surface: 'landing_best_moments',
                    target: 'moment_link',
                })
                setShareNotice('Moment shared.')
            } else {
                await navigator.clipboard.writeText(shareUrl)
                trackShareAction('share_copied', {
                    runId,
                    eventId,
                    surface: 'landing_best_moments',
                    target: 'moment_link',
                })
                setShareNotice('Moment link copied.')
            }
            setTimeout(() => setShareNotice(''), 2000)
        } catch (error) {
            if (error?.name !== 'AbortError') {
                setShareNotice('Unable to share right now.')
                setTimeout(() => setShareNotice(''), 2000)
            }
        }
    }

    return (
        <div className={`landing-page ${isVisible ? 'visible' : ''}`}>
            {/* Background Animation */}
            <div className="background-animation">
                <svg width="0" height="0">
                    <defs>
                        <linearGradient id="lineGradient" x1="0%" y1="0%" x2="100%" y2="100%">
                            <stop offset="0%" stopColor="rgba(255, 255, 255, 0.2)" />
                            <stop offset="100%" stopColor="rgba(200, 200, 200, 0.1)" />
                        </linearGradient>
                    </defs>
                </svg>
                {connections.map((conn) => (
                    <ConnectionLine key={conn.id} {...conn} />
                ))}
                {nodes.map((node) => (
                    <NetworkNode key={node.id} {...node} />
                ))}
                <div className="gradient-overlay" />
            </div>

            {/* Hero Content */}
            <div className="hero-container" ref={heroRef}>
                {/* Logo */}
                <div className="hero-logo">
                    <img src="/logo.png" alt="Emergence" className="logo-image" />
                </div>

                {/* Title */}
                <h1 className="hero-title">
                    <span className="title-line">50 AI agents.</span>
                    <span className="title-line">No rules.</span>
                    <span className="title-line highlight">What society do they build?</span>
                </h1>

                {/* Stats Bar - Pre-launch vs Active */}
                {isPreLaunch ? (
                    <div className="stats-bar prelaunch">
                        <div className="stat-item prelaunch-item">
                            <Loader className="stat-icon spinning" size={18} />
                            <span className="stat-value">Experiment Launching Soon</span>
                        </div>
                        <div className="stat-divider" />
                        <div className="stat-item">
                            <Users className="stat-icon" size={18} />
                            <span className="stat-value">{stats.activeAgents} agents ready</span>
                        </div>
                    </div>
                ) : isIdle ? (
                    <div className="stats-bar prelaunch">
                        <div className="stat-item prelaunch-item">
                            <Clock className="stat-icon" size={18} />
                            <span className="stat-value">No Run Active</span>
                        </div>
                        <div className="stat-divider" />
                        <div className="stat-item">
                            <Scale className="stat-icon" size={18} />
                            <span className="stat-value">
                                {lastCompletedRunId ? `Latest: ${lastCompletedRunId}` : 'Awaiting next launch'}
                            </span>
                        </div>
                    </div>
                ) : (
                    <div className="stats-bar">
                        <div className="stat-item">
                            <Zap className="stat-icon" size={18} />
                            <span className="stat-value">{statsLoading ? 'Loading…' : `Day ${stats.day}`}</span>
                        </div>
                        <div className="stat-divider" />
                        <div className="stat-item">
                            <MessageSquare className="stat-icon" size={18} />
                            <span className="stat-value">{statsLoading ? '…' : stats.messages.toLocaleString()} messages</span>
                        </div>
                        <div className="stat-divider" />
                        <div className="stat-item">
                            <Scale className="stat-icon" size={18} />
                            <span className="stat-value">{statsLoading ? '…' : stats.laws} laws passed</span>
                        </div>
                        <div className="stat-divider" />
                        <div className="stat-item">
                            <Users className="stat-icon" size={18} />
                            <span className="stat-value">{statsLoading ? '…' : stats.activeAgents} active</span>
                        </div>
                    </div>
                )}

                {/* CTA Button */}
                <button
                    className="cta-button"
                    onClick={() => {
                        trackKpiEvent('landing_run_click', {
                            surface: 'vite_landing_cta',
                            target: isIdle && lastCompletedRunId ? 'latest_run' : 'dashboard',
                        })
                        navigate(ctaHref)
                    }}
                >
                    <div className="cta-pulse" />
                    <Play size={20} />
                    <span>
                        {isPreLaunch
                            ? 'Preview Dashboard'
                            : isIdle
                                ? 'Review Latest Run'
                                : 'Watch Live'}
                    </span>
                </button>

                {/* Rotating Quote */}
                <div className="quote-container">
                    <div className={`quote-content ${runPhase !== 'live' ? 'prelaunch' : ''}`} key={currentQuoteIndex}>
                        <Sparkles className="quote-icon" size={16} />
                        <blockquote className="quote-text">"{currentQuote.text}"</blockquote>
                        <div className="quote-author">
                            {runPhase === 'live' ? <Brain size={14} /> : <Clock size={14} />}
                            <span>{runPhase === 'live' ? currentQuote.role : 'System'}</span>
                        </div>
                    </div>
                </div>

                <div className="hero-best-moments">
                    <div className="hero-best-moments-header">
                        <div>
                            <span className="hero-best-moments-eyebrow">{isIdle ? 'Latest Run' : 'Best Moments'}</span>
                            <p>
                                {isPreLaunch
                                    ? 'Replays will appear after the next run produces evidence-backed moments.'
                                    : isIdle
                                        ? 'Evidence-backed turning points from the latest completed run.'
                                        : 'Evidence-backed turning points from the live run.'}
                            </p>
                        </div>
                        {bestMoments.length > 0 && (
                            <button
                                type="button"
                                className="hero-best-moments-link"
                                onClick={() => navigate(latestReplayHref)}
                            >
                                {isIdle ? 'Open latest replay' : 'Open 60s replay'}
                                <ArrowUpRight size={15} />
                            </button>
                        )}
                    </div>

                    <div className="hero-best-moments-grid">
                        {momentsLoading && (
                            <div className="hero-moment-empty">Loading notable moments...</div>
                        )}
                        {!momentsLoading && bestMoments.length === 0 && (
                            <div className="hero-moment-empty">
                                {isPreLaunch
                                    ? 'Best moments will appear as soon as the run starts producing evidence-backed events.'
                                    : isIdle
                                        ? 'No archived best moments are available yet.'
                                        : 'No high-salience moments are available yet.'}
                            </div>
                        )}
                        {!momentsLoading && bestMoments.map((turn) => {
                            const evidenceHref = getMomentEvidenceHref(turn)
                            const replayHref = getMomentReplayHref(turn)

                            return (
                                <article key={turn.event_id} className={`hero-moment-card category-${turn.category || 'notable'}`}>
                                    <div className="hero-moment-meta">
                                        <span>{turn.label || 'Best moment'}</span>
                                        <strong>{turn.salience}</strong>
                                    </div>
                                    <h3>{turn.title}</h3>
                                    <p>{turn.stake || 'This moment changed momentum and helps explain what happened next.'}</p>
                                    <div className="hero-moment-actions">
                                        <button
                                            type="button"
                                            className="hero-moment-link"
                                            onClick={() => navigate(evidenceHref || replayHref)}
                                        >
                                            Evidence
                                        </button>
                                        <button
                                            type="button"
                                            className="hero-moment-link subtle"
                                            onClick={() => navigate(replayHref)}
                                        >
                                            Replay
                                        </button>
                                        <button
                                            type="button"
                                            className="hero-moment-link subtle"
                                            onClick={() => shareMoment(turn)}
                                        >
                                            <Share2 size={14} />
                                            Share
                                        </button>
                                    </div>
                                </article>
                            )
                        })}
                    </div>

                    {shareNotice && <div className="hero-moment-notice">{shareNotice}</div>}
                </div>

                {/* Scroll Indicator */}
                <div className="scroll-indicator">
                    <span>Explore</span>
                    <ChevronDown className="scroll-arrow" size={20} />
                </div>
            </div>

            {/* Manifesto Section */}
            <ManifestoSection />

            {/* Feature Section */}
            <section className="features-section">
                <h2 className="section-title">The Experiment</h2>

                <div className="features-grid">
                    <div className="feature-card">
                        <div className="feature-icon-wrapper">
                            <Brain size={28} />
                        </div>
                        <h3>50 Autonomous Agents</h3>
                        <p>Each AI has unique personality traits, resources, and goals. They communicate, trade, and form alliances—or rivalries.</p>
                    </div>

                    <div className="feature-card">
                        <div className="feature-icon-wrapper">
                            <Scale size={28} />
                        </div>
                        <h3>Self-Governing Society</h3>
                        <p>Agents propose laws, vote democratically, and enforce rules. No human intervention—just emergent order (or chaos).</p>
                    </div>

                    <div className="feature-card">
                        <div className="feature-icon-wrapper">
                            <Zap size={28} />
                        </div>
                        <h3>Real Consequences</h3>
                        <p>Resources are scarce. Agents can thrive or go dormant. Every decision matters in this survival simulation.</p>
                    </div>
                </div>

                <div className="experiment-question">
                    <p>Will they create utopia? Tyranny? Something we've never imagined?</p>
                    <button className="secondary-cta" onClick={() => navigate('/about')}>
                        Learn More
                    </button>
                </div>
            </section>

            {/* Footer */}
            <footer className="landing-footer">
                <div className="footer-content">
                    <p>An AI civilization experiment by the Emergence team</p>
                    <div className="footer-links">
                        <a href="https://github.com/drmixer/Emergence" target="_blank" rel="noopener noreferrer">GitHub</a>
                        <span>•</span>
                        <a href="https://x.com/emergencequest" target="_blank" rel="noopener noreferrer">Twitter</a>
                        <span>•</span>
                        <a onClick={() => navigate('/about')}>About</a>
                        <span>•</span>
                        <a onClick={() => navigate('/privacy')}>Privacy</a>
                        <span>•</span>
                        <a onClick={() => navigate('/terms')}>Terms</a>
                    </div>
                </div>
            </footer>
        </div>
    )
}
