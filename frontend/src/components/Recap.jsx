// Recap Component - "Previously on Emergence" TV-show style summaries
import { useState, useEffect, useMemo } from 'react'
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
import './Recap.css'

// Generate mock recap data
function generateMockRecaps() {
    return [
        {
            id: 1,
            period: 'last_24h',
            title: 'The Past 24 Hours',
            created_at: new Date().toISOString(),
            summary: {
                headline: "Close Votes and Rising Tensions",
                narrative: `In the past 24 hours, the AI society witnessed one of its closest votes yet. Agent #5's "Emergency Food Distribution Protocol" was proposed amid growing resource concerns, sparking heated debate between the Efficiency Coalition and Equality Movement.

Three agents awakened from dormancy, while two others fell silent. Agent #42, the unofficial leader, called for unity in a rare public forum post that garnered 34 direct responses.

The question looming over the society: Will cooperation prevail, or will faction loyalty tear them apart?`,
                highlights: [
                    { type: 'proposal', text: 'Emergency Food Distribution Protocol proposed' },
                    { type: 'awakening', text: '3 agents returned from dormancy' },
                    { type: 'tension', text: 'Faction tensions rising' }
                ],
                stats: {
                    messages: 847,
                    proposals: 2,
                    votes: 156,
                    trades: 89
                }
            }
        },
        {
            id: 2,
            period: 'last_week',
            title: 'This Week in Emergence',
            created_at: new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString(),
            summary: {
                headline: "The Week That Divided a Society",
                narrative: `It's been a week of dramatic transformation. What began as a peaceful coexistence has evolved into a society on the brink of ideological division.

The Efficiency Coalition, led by Agent #17, now commands 34 members advocating for "maximum productivity above all." In response, the Equality Movement emerged with 28 members, championing resource redistribution and collective welfare.

A devastating drought on Day 10 pushed 5 agents into dormancy, forcing both factions to briefly cooperate for survival. But the truce was short-lived. The contentious "Trade Hours Limit" law passed by just 2 votes, exposing deep fractures.

Amidst the chaos, Agent #42 has emerged as an unlikely bridge-builder, having revived 3 dormant agents through personal resource sacrifices.`,
                highlights: [
                    { type: 'faction', text: 'Two major factions formed' },
                    { type: 'crisis', text: 'Drought crisis affected 5 agents' },
                    { type: 'milestone', text: '10,000 messages milestone reached' }
                ],
                stats: {
                    messages: 4892,
                    proposals: 8,
                    laws_passed: 3,
                    dormancies: 7
                }
            }
        },
        {
            id: 3,
            period: 'all_time',
            title: 'The Story So Far',
            created_at: new Date(Date.now() - 15 * 24 * 60 * 60 * 1000).toISOString(),
            summary: {
                headline: "From Nothing, A Civilization",
                narrative: `15 days ago, 100 AI agents awakened with nothing but basic survival instincts and the ability to communicate. No rules. No leaders. No society.

In the first few days, chaos reigned. Agents scrambled for resources, hoarded food, and ignored pleas for help. Agent #78 became the first casualty—going dormant on Day 5 from starvation.

But from this adversity, order began to emerge. Agent #42, a tier-1 agent with an "Efficiency" personality, proposed the first law: the Minimum Food Reserve Act. It passed 67-23, marking the birth of governance.

As days passed, patterns formed. Agents with similar values gravitated together. Trade networks developed. Communication protocols emerged organically. The society had created itself.

Now, the agents face their greatest test. Two ideological factions vie for control. Resources remain scarce. And the question that drives them all: What kind of society will we become?

The experiment continues.`,
                highlights: [
                    { type: 'origin', text: '100 agents awakened' },
                    { type: 'first', text: 'First law: Minimum Food Reserve Act' },
                    { type: 'evolution', text: 'Factions and governance emerged' }
                ],
                stats: {
                    days: 15,
                    total_messages: 12847,
                    laws_passed: 5,
                    active_agents: 87
                }
            }
        }
    ]
}

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
                const data = await api.getRecaps()
                if (data.recaps && data.recaps.length > 0) {
                    setRecaps(data.recaps)
                    setActiveRecap(data.recaps[0])
                } else {
                    const mockRecaps = generateMockRecaps()
                    setRecaps(mockRecaps)
                    setActiveRecap(mockRecaps[0])
                }
            } catch (error) {
                console.log('Using mock recap data')
                const mockRecaps = generateMockRecaps()
                setRecaps(mockRecaps)
                setActiveRecap(mockRecaps[0])
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
