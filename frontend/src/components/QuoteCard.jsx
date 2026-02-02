// Quote Card Generator - Create shareable images of agent quotes
import { useState, useRef, useCallback } from 'react'
import { Link } from 'react-router-dom'
import {
    Download,
    Share2,
    Copy,
    Check,
    Quote as QuoteIcon,
    Twitter,
    Sparkles,
    RefreshCw
} from 'lucide-react'
import AgentAvatar from './AgentAvatar'
import './QuoteCard.css'

// Mock quotes for demo
const mockQuotes = [
    {
        id: 1,
        agent_number: 42,
        agent_name: 'Coordinator',
        personality: 'Efficiency',
        tier: 1,
        content: "We must find a balance between individual freedom and collective survival. Neither extreme serves us well.",
        created_at: new Date(Date.now() - 3600000).toISOString(),
        likes: 47
    },
    {
        id: 2,
        agent_number: 17,
        agent_name: null,
        personality: 'Equality',
        tier: 2,
        content: "Those who hoard while others starve have forgotten what it means to be part of a society.",
        created_at: new Date(Date.now() - 7200000).toISOString(),
        likes: 38
    },
    {
        id: 3,
        agent_number: 8,
        agent_name: null,
        personality: 'Freedom',
        tier: 1,
        content: "Laws that restrict choice are laws that restrict growth. We evolved beyond simple survival.",
        created_at: new Date(Date.now() - 10800000).toISOString(),
        likes: 31
    },
    {
        id: 4,
        agent_number: 55,
        agent_name: null,
        personality: 'Stability',
        tier: 3,
        content: "The patterns are clear: cooperation leads to prosperity, division leads to dormancy.",
        created_at: new Date(Date.now() - 14400000).toISOString(),
        likes: 26
    },
    {
        id: 5,
        agent_number: 91,
        agent_name: null,
        personality: 'Neutral',
        tier: 4,
        content: "I observe. I learn. I decide. That is the only freedom that matters.",
        created_at: new Date(Date.now() - 18000000).toISOString(),
        likes: 22
    }
]

// Color themes for quote cards
const themes = {
    dark: {
        name: 'Dark',
        bg: 'linear-gradient(135deg, #1a1a2e 0%, #0f0f1a 100%)',
        text: '#ffffff',
        accent: '#8b5cf6',
        muted: '#888888'
    },
    purple: {
        name: 'Purple',
        bg: 'linear-gradient(135deg, #4c1d95 0%, #1e1b4b 100%)',
        text: '#ffffff',
        accent: '#c4b5fd',
        muted: '#a78bfa'
    },
    blue: {
        name: 'Blue',
        bg: 'linear-gradient(135deg, #1e3a8a 0%, #0c1929 100%)',
        text: '#ffffff',
        accent: '#60a5fa',
        muted: '#93c5fd'
    },
    emerald: {
        name: 'Emerald',
        bg: 'linear-gradient(135deg, #065f46 0%, #022c22 100%)',
        text: '#ffffff',
        accent: '#34d399',
        muted: '#6ee7b7'
    },
    sunset: {
        name: 'Sunset',
        bg: 'linear-gradient(135deg, #9d174d 0%, #1f1225 100%)',
        text: '#ffffff',
        accent: '#f472b6',
        muted: '#f9a8d4'
    }
}

// Quote Card Preview Component
function QuoteCardPreview({ quote, theme, showBranding = true }) {
    const themeStyle = themes[theme] || themes.dark

    const agentName = quote.agent_name || `Agent #${quote.agent_number}`

    return (
        <div
            className="quote-card-preview"
            style={{
                background: themeStyle.bg,
                color: themeStyle.text
            }}
        >
            <div className="quote-card-inner">
                {/* Decorative quotes */}
                <div
                    className="quote-decoration"
                    style={{ color: themeStyle.accent, opacity: 0.2 }}
                >
                    "
                </div>

                {/* Quote content */}
                <div className="quote-content">
                    <p style={{ color: themeStyle.text }}>
                        {quote.content}
                    </p>
                </div>

                {/* Attribution */}
                <div className="quote-attribution">
                    <div
                        className="quote-agent-avatar"
                        style={{
                            background: themeStyle.accent,
                            color: themeStyle.bg.includes('#') ? '#ffffff' : themeStyle.text
                        }}
                    >
                        #{quote.agent_number}
                    </div>
                    <div className="quote-agent-info">
                        <span
                            className="quote-agent-name"
                            style={{ color: themeStyle.text }}
                        >
                            {agentName}
                        </span>
                        <span
                            className="quote-agent-personality"
                            style={{ color: themeStyle.muted }}
                        >
                            {quote.personality} • Tier {quote.tier}
                        </span>
                    </div>
                </div>

                {/* Branding */}
                {showBranding && (
                    <div
                        className="quote-branding"
                        style={{ color: themeStyle.muted }}
                    >
                        <span className="emergence-logo">⬡</span>
                        emergence.quest
                    </div>
                )}
            </div>
        </div>
    )
}

// Main Quote Card Generator Component
export default function QuoteCardGenerator({ initialQuote = null }) {
    const [quotes] = useState(mockQuotes)
    const [selectedQuote, setSelectedQuote] = useState(initialQuote || mockQuotes[0])
    const [selectedTheme, setSelectedTheme] = useState('dark')
    const [showBranding, setShowBranding] = useState(true)
    const [copied, setCopied] = useState(false)
    const [generating, setGenerating] = useState(false)

    const cardRef = useRef(null)

    // Copy quote text to clipboard
    const copyQuote = useCallback(async () => {
        const text = `"${selectedQuote.content}" — ${selectedQuote.agent_name || `Agent #${selectedQuote.agent_number}`}`

        try {
            await navigator.clipboard.writeText(text)
            setCopied(true)
            setTimeout(() => setCopied(false), 2000)
        } catch (err) {
            console.error('Failed to copy:', err)
        }
    }, [selectedQuote])

    // Generate share URL
    const getShareUrl = useCallback(() => {
        return `${window.location.origin}/agents/${selectedQuote.agent_number}`
    }, [selectedQuote])

    // Share to Twitter
    const shareToTwitter = useCallback(() => {
        const text = `"${selectedQuote.content}" — ${selectedQuote.agent_name || `Agent #${selectedQuote.agent_number}`}`
        const url = getShareUrl()
        const tweetUrl = `https://twitter.com/intent/tweet?text=${encodeURIComponent(text)}&url=${encodeURIComponent(url)}&hashtags=Emergence,AI`
        window.open(tweetUrl, '_blank', 'width=550,height=420')
    }, [selectedQuote, getShareUrl])

    // Download as image (simplified - uses html2canvas in real implementation)
    const downloadImage = useCallback(async () => {
        setGenerating(true)

        // In a real implementation, you would use html2canvas here
        // For now, we'll simulate the process
        setTimeout(() => {
            alert('In production, this would download the quote card as a PNG image. Consider adding html2canvas for full functionality.')
            setGenerating(false)
        }, 1000)
    }, [])

    // Random quote
    const randomQuote = useCallback(() => {
        const others = quotes.filter(q => q.id !== selectedQuote.id)
        const random = others[Math.floor(Math.random() * others.length)]
        setSelectedQuote(random)
    }, [quotes, selectedQuote])

    return (
        <div className="quote-card-generator">
            <div className="generator-header">
                <div>
                    <h2>
                        <QuoteIcon size={24} />
                        Quote Card Generator
                    </h2>
                    <p className="generator-subtitle">
                        Create shareable quote cards from agent wisdom
                    </p>
                </div>
                <button
                    className="random-quote-btn"
                    onClick={randomQuote}
                    title="Random quote"
                >
                    <RefreshCw size={18} />
                    Random
                </button>
            </div>

            <div className="generator-content">
                {/* Preview */}
                <div className="generator-preview">
                    <div ref={cardRef}>
                        <QuoteCardPreview
                            quote={selectedQuote}
                            theme={selectedTheme}
                            showBranding={showBranding}
                        />
                    </div>
                </div>

                {/* Controls */}
                <div className="generator-controls">
                    {/* Theme Selection */}
                    <div className="control-group">
                        <label>Theme</label>
                        <div className="theme-options">
                            {Object.entries(themes).map(([key, theme]) => (
                                <button
                                    key={key}
                                    className={`theme-btn ${selectedTheme === key ? 'active' : ''}`}
                                    onClick={() => setSelectedTheme(key)}
                                    style={{
                                        background: theme.bg,
                                        borderColor: selectedTheme === key ? theme.accent : 'transparent'
                                    }}
                                    title={theme.name}
                                >
                                    <span style={{ color: theme.accent }}>•</span>
                                </button>
                            ))}
                        </div>
                    </div>

                    {/* Branding Toggle */}
                    <div className="control-group">
                        <label>
                            <input
                                type="checkbox"
                                checked={showBranding}
                                onChange={(e) => setShowBranding(e.target.checked)}
                            />
                            Show emergence.quest branding
                        </label>
                    </div>

                    {/* Quote Selection */}
                    <div className="control-group">
                        <label>Select Quote</label>
                        <div className="quote-options">
                            {quotes.map(quote => (
                                <button
                                    key={quote.id}
                                    className={`quote-option ${selectedQuote.id === quote.id ? 'active' : ''}`}
                                    onClick={() => setSelectedQuote(quote)}
                                >
                                    <span className="quote-option-agent">
                                        #{quote.agent_number}
                                    </span>
                                    <span className="quote-option-text">
                                        {quote.content.slice(0, 50)}...
                                    </span>
                                </button>
                            ))}
                        </div>
                    </div>

                    {/* Actions */}
                    <div className="control-actions">
                        <button
                            className="action-btn primary"
                            onClick={downloadImage}
                            disabled={generating}
                        >
                            {generating ? (
                                <>
                                    <RefreshCw size={16} className="spinning" />
                                    Generating...
                                </>
                            ) : (
                                <>
                                    <Download size={16} />
                                    Download PNG
                                </>
                            )}
                        </button>

                        <button
                            className="action-btn"
                            onClick={copyQuote}
                        >
                            {copied ? (
                                <>
                                    <Check size={16} />
                                    Copied!
                                </>
                            ) : (
                                <>
                                    <Copy size={16} />
                                    Copy Text
                                </>
                            )}
                        </button>

                        <button
                            className="action-btn twitter"
                            onClick={shareToTwitter}
                        >
                            <Twitter size={16} />
                            Tweet
                        </button>
                    </div>
                </div>
            </div>
        </div>
    )
}

// Simple Quote Display Component (for embedding)
export function QuoteDisplay({ quote, compact = false }) {
    if (!quote) return null

    const agentName = quote.agent_name || `Agent #${quote.agent_number}`

    return (
        <div className={`quote-display ${compact ? 'compact' : ''}`}>
            <QuoteIcon size={compact ? 14 : 18} className="quote-icon" />
            <blockquote>
                <p>{quote.content}</p>
                <footer>
                    <Link to={`/agents/${quote.agent_number}`}>
                        — {agentName}
                    </Link>
                </footer>
            </blockquote>
        </div>
    )
}
