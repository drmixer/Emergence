// Quote Card Generator - Create shareable images of agent quotes
import { useEffect, useState, useRef, useCallback } from 'react'
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
import { api } from '../services/api'
import { formatAgentDisplayLabel } from '../utils/agentIdentity'

function titleCase(s) {
    if (!s) return ''
    return String(s).charAt(0).toUpperCase() + String(s).slice(1)
}

function messageToQuote(msg) {
    if (!msg?.id || !msg?.content || !msg?.author?.agent_number) return null
    return {
        id: msg.id,
        agent_number: msg.author.agent_number,
        agent_name: msg.author.display_name,
        personality: titleCase(msg.author.personality_type),
        tier: msg.author.tier,
        content: msg.content,
        created_at: msg.created_at,
    }
}

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

    const agentName = formatAgentDisplayLabel(quote)

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
    const [quotes, setQuotes] = useState([])
    const [selectedQuote, setSelectedQuote] = useState(initialQuote)
    const [selectedTheme, setSelectedTheme] = useState('dark')
    const [showBranding, setShowBranding] = useState(true)
    const [copied, setCopied] = useState(false)
    const [generating, setGenerating] = useState(false)
    const [loading, setLoading] = useState(true)

    const cardRef = useRef(null)

    useEffect(() => {
        async function load() {
            setLoading(true)
            try {
                const [posts, replies] = await Promise.all([
                    api.getMessages(50),
                    api.fetch('/api/messages?message_type=forum_reply&limit=50').catch(() => []),
                ])

                const combined = []
                for (const m of [...(Array.isArray(posts) ? posts : []), ...(Array.isArray(replies) ? replies : [])]) {
                    const q = messageToQuote(m)
                    if (!q) continue
                    const len = q.content.length
                    if (len < 20 || len > 320) continue
                    combined.push(q)
                }

                setQuotes(combined)
                if (combined.length > 0) {
                    setSelectedQuote((prev) => prev || combined[0])
                }
            } catch {
                setQuotes([])
            } finally {
                setLoading(false)
            }
        }
        load()
    }, [])

    // Copy quote text to clipboard
    const copyQuote = useCallback(async () => {
        if (!selectedQuote) return
        const text = `"${selectedQuote.content}" — ${formatAgentDisplayLabel(selectedQuote)}`

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
        if (!selectedQuote) return window.location.origin
        return `${window.location.origin}/agents/${selectedQuote.agent_number}`
    }, [selectedQuote])

    // Share to Twitter
    const shareToTwitter = useCallback(() => {
        if (!selectedQuote) return
        const text = `"${selectedQuote.content}" — ${formatAgentDisplayLabel(selectedQuote)}`
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
        if (!selectedQuote || quotes.length < 2) return
        const others = quotes.filter(q => q.id !== selectedQuote.id)
        if (others.length === 0) return
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
                {loading ? (
                    <div className="empty-state">Loading quotes…</div>
                ) : !selectedQuote ? (
                    <div className="empty-state">No quotes yet.</div>
                ) : (
                    <>
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
                                    className={`quote-option ${selectedQuote?.id === quote.id ? 'active' : ''}`}
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
                    </>
                )}
            </div>
        </div>
    )
}

// Simple Quote Display Component (for embedding)
export function QuoteDisplay({ quote, compact = false }) {
    if (!quote) return null

    const agentName = formatAgentDisplayLabel(quote)

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
