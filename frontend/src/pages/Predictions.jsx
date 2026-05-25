import { useState, useEffect } from 'react'
import {
    TrendingUp,
    TrendingDown,
    Trophy,
    Coins,
    Clock,
    CheckCircle,
    XCircle,
    Target,
    Zap,
    Users,
    AlertTriangle,
    ChevronRight,
    Star,
    Award,
    BarChart3,
    Sparkles
} from 'lucide-react'
import { formatDistanceToNow } from 'date-fns'
import { api, resolveApiBase } from '../services/api'
import GlossaryTooltip from '../components/GlossaryTooltip'
import NoActiveRunNotice from '../components/NoActiveRunNotice'

// API base URL
const API_BASE = resolveApiBase()

// Fetch helper with timeout
const fetchJson = async (endpoint, options = {}) => {
    const controller = new AbortController()
    const timeoutId = setTimeout(() => controller.abort(), 5000) // 5 second timeout

    try {
        const response = await fetch(`${API_BASE}${endpoint}`, { ...options, signal: controller.signal })
        clearTimeout(timeoutId)
        if (!response.ok) throw new Error(`API error: ${response.status}`)
        return await response.json()
    } catch (error) {
        clearTimeout(timeoutId)
        throw error
    }
}

// Market type icons
const marketTypeIcons = {
    proposal_pass: Target,
    agent_dormant: AlertTriangle,
    resource_goal: Zap,
    law_count: Award,
    custom: Star
}

// Market type labels
const marketTypeLabels = {
    proposal_pass: 'Proposal Vote',
    agent_dormant: 'Agent Status',
    resource_goal: 'Resource Goal',
    law_count: 'Law Milestone',
    custom: 'Special Event'
}

export default function Predictions() {
    const [markets, setMarkets] = useState([])
    const [leaderboard, setLeaderboard] = useState([])
    const [userStats, setUserStats] = useState({
        balance: 100,
        bets_made: 0,
        bets_won: 0,
        win_rate: 0,
        rank: null
    })
    const [activeTab, setActiveTab] = useState('open')
    const [selectedMarket, setSelectedMarket] = useState(null)
    const [betAmount, setBetAmount] = useState(10)
    const [betPrediction, setBetPrediction] = useState(null)
    const [isPlacingBet, setIsPlacingBet] = useState(false)
    const [betError, setBetError] = useState(null)
    const [betSuccess, setBetSuccess] = useState(null)
    const [loading, setLoading] = useState(true)
    const [scope, setScope] = useState(null)

    // Fetch data on mount
    useEffect(() => {
        loadData()
    }, [])

    const loadData = async () => {
        setLoading(true)
        try {
            const [overview, openMarketsData, resolvedMarketsData, leaderboardData, me] = await Promise.all([
                fetchJson('/api/analytics/overview').catch(() => null),
                api.getPredictionMarkets('open', 50),
                api.getPredictionMarkets('resolved', 50),
                fetchJson('/api/predictions/leaderboard'),
                fetchJson('/api/predictions/me', { credentials: 'include' }).catch(() => null),
            ])

            setScope(overview?.scope || null)
            setMarkets([
                ...(Array.isArray(openMarketsData) ? openMarketsData : []),
                ...(Array.isArray(resolvedMarketsData) ? resolvedMarketsData : []),
            ])
            setLeaderboard(Array.isArray(leaderboardData) ? leaderboardData : [])
            if (me) setUserStats(me)
        } catch (_error) {
            setScope(null)
            setMarkets([])
            setLeaderboard([])
        } finally {
            setLoading(false)
        }
    }

    const filteredMarkets = markets.filter(m => {
        if (activeTab === 'open') return m.status === 'open'
        if (activeTab === 'resolved') return m.status === 'resolved'
        return true
    })
    const inactiveRun = !loading && scope?.simulation_active === false
    const lastCompletedRunId = String(scope?.last_completed_run_id || '').trim()

    useEffect(() => {
        if (inactiveRun && activeTab === 'open') {
            setActiveTab('resolved')
        }
    }, [activeTab, inactiveRun])

    const openBetModal = (market) => {
        if (inactiveRun) return
        setSelectedMarket(market)
        setBetAmount(10)
        setBetPrediction(null)
        setBetError(null)
        setBetSuccess(null)
    }

    const closeBetModal = () => {
        setSelectedMarket(null)
        setBetAmount(10)
        setBetPrediction(null)
        setBetError(null)
        setBetSuccess(null)
    }

    const placeBet = async () => {
        if (!selectedMarket || !betPrediction || betAmount < 1) return

        setIsPlacingBet(true)
        setBetError(null)

        try {
            const response = await fetch(`${API_BASE}/api/predictions/markets/${selectedMarket.id}/bet`, {
                method: 'POST',
                credentials: 'include',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    prediction: betPrediction,
                    amount: betAmount
                })
            })

            if (response.ok) {
                setBetSuccess(`Pick placed: ${betAmount} EP on ${betPrediction.toUpperCase()}`)
                // Refresh data
                setTimeout(() => {
                    closeBetModal()
                    loadData()
                }, 2000)
            } else {
                const error = await response.json()
                setBetError(error.detail || 'Failed to place bet')
            }
        } catch (_error) {
            setBetError('Failed to place bet')
        }

        setIsPlacingBet(false)
    }

    // Calculate potential payout
    const calculatePayout = (market, prediction, amount) => {
        const totalPool = market.total_yes_amount + market.total_no_amount + amount
        const winningPool = prediction === 'yes'
            ? market.total_yes_amount + amount
            : market.total_no_amount + amount
        const odds = totalPool / winningPool
        return (amount * odds).toFixed(2)
    }

    return (
        <div className="predictions-page">
            <div className="page-header">
                <h1>
                    <TrendingUp size={32} />
                    Prediction Market
                </h1>
                <p className="page-description">
                    Audience-side picks about what named agents will do next. Picks do not influence the simulation.
                </p>
            </div>

            {inactiveRun && (
                <NoActiveRunNotice
                    message="Prediction markets are closed while no run is active, so old markets cannot accept new picks."
                    lastCompletedRunId={lastCompletedRunId}
                />
            )}

            <div className="prediction-intro">
                <div>
                    <strong>{inactiveRun ? 'Markets are paused between runs.' : 'Come back when these settle.'}</strong>
                    <p>
                        {inactiveRun
                            ? 'Resolved markets remain available for review. New prediction hooks open when the next simulation starts.'
                            : <>Each live hook follows a named agent under visible pressure: aid requests, trades, proposal votes, and <GlossaryTooltip termKey="at-risk">at-risk</GlossaryTooltip> agent decisions.</>}
                    </p>
                </div>
                <span className="prediction-intro-note">Virtual EP only. No effect on agent incentives.</span>
            </div>

            {/* User Stats Bar */}
            {!inactiveRun && <div className="user-stats-bar">
                <div className="stat-item balance">
                    <Coins size={20} className="stat-icon" />
                    <div className="stat-content">
                        <span className="stat-value">{userStats.balance.toFixed(0)} EP</span>
                        <span className="stat-label">Balance</span>
                    </div>
                </div>
                <div className="stat-item">
                    <BarChart3 size={20} className="stat-icon" />
                    <div className="stat-content">
                        <span className="stat-value">{userStats.bets_made}</span>
                        <span className="stat-label">Picks Made</span>
                    </div>
                </div>
                <div className="stat-item">
                    <CheckCircle size={20} className="stat-icon" />
                    <div className="stat-content">
                        <span className="stat-value">{userStats.bets_won}</span>
                        <span className="stat-label">Wins</span>
                    </div>
                </div>
                <div className="stat-item">
                    <Target size={20} className="stat-icon" />
                    <div className="stat-content">
                        <span className="stat-value">{userStats.win_rate}%</span>
                        <span className="stat-label">Win Rate</span>
                    </div>
                </div>
                {userStats.rank && (
                    <div className="stat-item rank">
                        <Trophy size={20} className="stat-icon" />
                        <div className="stat-content">
                            <span className="stat-value">#{userStats.rank}</span>
                            <span className="stat-label">Rank</span>
                        </div>
                    </div>
                )}
            </div>}

            <div className="predictions-layout">
                {/* Markets Section */}
                <div className="markets-section">
                    {/* Tabs */}
                    <div className="market-tabs">
                        <button
                            className={`tab-btn ${activeTab === 'open' ? 'active' : ''}`}
                            disabled={inactiveRun}
                            onClick={() => setActiveTab('open')}
                            title={inactiveRun ? 'Open markets return when a run is active' : undefined}
                        >
                            <Sparkles size={16} />
                            Open Predictions
                            <span className="count">{markets.filter(m => m.status === 'open').length}</span>
                        </button>
                        <button
                            className={`tab-btn ${activeTab === 'resolved' ? 'active' : ''}`}
                            onClick={() => setActiveTab('resolved')}
                        >
                            <CheckCircle size={16} />
                            Resolved
                            <span className="count">{markets.filter(m => m.status === 'resolved').length}</span>
                        </button>
                    </div>

                    {/* Markets Grid */}
                    <div className="markets-grid">
                        {loading ? (
                            <div className="loading-state">
                                <div className="spinner"></div>
                                <span>Loading markets...</span>
                            </div>
                        ) : filteredMarkets.length === 0 ? (
                            <div className="empty-state">
                                <Target size={48} />
                                <p>
                                    {activeTab === 'open' && inactiveRun
                                        ? 'Open markets return when a run is active.'
                                        : activeTab === 'open'
                                            ? 'No high-quality live hooks are available yet. Predictions open only when there is a concrete agent decision, vote, aid request, or trade to resolve.'
                                            : 'No resolved markets found.'}
                                </p>
                            </div>
                        ) : (
                            filteredMarkets.map(market => {
                                const Icon = marketTypeIcons[market.market_type] || Star
                                const isOpen = market.status === 'open'
                                const yesPercent = (market.yes_probability * 100).toFixed(0)
                                const noPercent = (100 - market.yes_probability * 100).toFixed(0)
                                const contextText = market.description || market.why_this_matters || market.stake || 'This prediction is tied to a visible agent action in the current run.'

                                return (
                                    <div
                                        key={market.id}
                                        className={`market-card ${market.status} ${inactiveRun ? 'paused' : ''}`}
                                        onClick={() => isOpen && !inactiveRun && openBetModal(market)}
                                    >
                                        <div className="market-header">
                                            <div className="market-badges">
                                                <div className={`market-type-badge ${market.market_type}`}>
                                                    <Icon size={14} />
                                                    {marketTypeLabels[market.market_type]}
                                                </div>
                                                {market.auto_generated && (
                                                    <div className="market-live-badge">
                                                        <Sparkles size={14} />
                                                        Live Hook
                                                    </div>
                                                )}
                                            </div>
                                            <div className="market-meta">
                                                {isOpen ? (
                                                    <span className="closes-in">
                                                        <Clock size={12} />
                                                        Closes {formatDistanceToNow(new Date(market.closes_at), { addSuffix: true })}
                                                    </span>
                                                ) : (
                                                    <span className={`outcome ${market.outcome}`}>
                                                        {market.outcome === 'yes' ? <CheckCircle size={14} /> : <XCircle size={14} />}
                                                        {market.outcome === 'yes' ? 'YES' : 'NO'}
                                                    </span>
                                                )}
                                            </div>
                                        </div>

                                        <div className="market-context">
                                            {market.related_agent_label && (
                                                <div className="market-context-row">
                                                    <span>Agent</span>
                                                    <p>{market.related_agent_label}</p>
                                                </div>
                                            )}
                                            <div className="market-context-row question">
                                                <span>Prediction</span>
                                                <div>
                                                    <h3 className="market-title">{market.title}</h3>
                                                </div>
                                            </div>
                                            <div className="market-context-row">
                                                <span>Context</span>
                                                <p>{contextText}</p>
                                            </div>
                                            <div className="market-context-row">
                                                <span>Resolves from</span>
                                                <p>{market.resolution_basis || 'Resolved after the run from public evidence and archived event data.'}</p>
                                            </div>
                                            {!isOpen && market.resolution_summary && (
                                                <div className="market-context-row">
                                                    <span>Settled by</span>
                                                    <p>{market.resolution_summary}</p>
                                                </div>
                                            )}
                                            <div className="market-context-row">
                                                <span>Evidence</span>
                                                {(market.resolution_evidence_href || (Array.isArray(market.evidence_links) && market.evidence_links.length > 0)) ? (
                                                    <div className="market-evidence">
                                                        {market.resolution_evidence_href && (
                                                            <a
                                                                href={market.resolution_evidence_href}
                                                                onClick={(event) => event.stopPropagation()}
                                                            >
                                                                Resolution event
                                                            </a>
                                                        )}
                                                        {(Array.isArray(market.evidence_links) ? market.evidence_links : []).map((link) => (
                                                            <a
                                                                key={`${market.id}-${link.href}`}
                                                                href={link.href}
                                                                onClick={(event) => event.stopPropagation()}
                                                            >
                                                                {link.label}
                                                            </a>
                                                        ))}
                                                    </div>
                                                ) : (
                                                    <p>Uses public run evidence when the market resolves.</p>
                                                )}
                                            </div>
                                        </div>

                                        <div className="probability-bar">
                                            <div className="prob-yes" style={{ width: `${yesPercent}%` }}>
                                                <span>YES {yesPercent}%</span>
                                            </div>
                                            <div className="prob-no" style={{ width: `${noPercent}%` }}>
                                                <span>NO {noPercent}%</span>
                                            </div>
                                        </div>

                                        <div className="market-footer">
                                            <div className="pool-info">
                                                <Coins size={14} />
                                                <span>{(market.total_yes_amount + market.total_no_amount).toFixed(0)} EP pool</span>
                                            </div>
                                            <div className="bet-count">
                                                <Users size={14} />
                                                <span>{market.bet_count} picks</span>
                                            </div>
                                            {isOpen && !inactiveRun && (
                                                <button className="bet-btn">
                                                    Make Pick <ChevronRight size={16} />
                                                </button>
                                            )}
                                        </div>
                                    </div>
                                )
                            })
                        )}
                    </div>
                </div>

                {/* Leaderboard Section */}
                <div className="leaderboard-section">
                    <div className="leaderboard-header">
                        <h2>
                            <Trophy size={24} />
                            Top Predictors
                        </h2>
                    </div>

                    <div className="leaderboard-list">
                        {leaderboard.slice(0, 10).map((entry, index) => (
                            <div key={entry.user_id} className={`leaderboard-entry rank-${index + 1}`}>
                                <div className="rank">
                                    {index === 0 && <span className="crown">👑</span>}
                                    {index === 1 && <span className="medal">🥈</span>}
                                    {index === 2 && <span className="medal">🥉</span>}
                                    {index > 2 && <span className="number">#{index + 1}</span>}
                                </div>
                                <div className="user-info">
                                    <span className="username">{entry.username || `Predictor ${entry.user_id.substring(0, 6)}`}</span>
                                    <span className="stats">
                                        {entry.win_rate}% win rate • {entry.bets_won}/{entry.bets_made} bets
                                    </span>
                                </div>
                                <div className="balance-info">
                                    <span className="balance">{entry.balance.toFixed(0)} EP</span>
                                    <span className={`profit ${entry.profit >= 0 ? 'positive' : 'negative'}`}>
                                        {entry.profit >= 0 ? '+' : ''}{entry.profit.toFixed(0)} EP
                                    </span>
                                </div>
                            </div>
                        ))}
                    </div>

                    <div className="leaderboard-footer">
                        <p className="leaderboard-note">
                            Rankings update after each market resolves
                        </p>
                    </div>
                </div>
            </div>

            {/* Bet Modal */}
            {selectedMarket && !inactiveRun && (
                <div className="modal-overlay" onClick={closeBetModal}>
                    <div className="bet-modal" onClick={e => e.stopPropagation()}>
                        <button className="modal-close" onClick={closeBetModal}>&times;</button>

                        <div className="modal-header">
                            <h2>Make Your Pick</h2>
                            <p className="modal-subtitle">{selectedMarket.title}</p>
                            {selectedMarket.resolution_basis && (
                                <p className="modal-resolution">{selectedMarket.resolution_basis}</p>
                            )}
                        </div>

                        <div className="bet-options">
                            <button
                                className={`bet-option yes ${betPrediction === 'yes' ? 'selected' : ''}`}
                                onClick={() => setBetPrediction('yes')}
                            >
                                <TrendingUp size={24} />
                                <span className="option-label">YES</span>
                                <span className="option-odds">{(selectedMarket.yes_probability * 100).toFixed(0)}%</span>
                            </button>
                            <span className="or-divider">or</span>
                            <button
                                className={`bet-option no ${betPrediction === 'no' ? 'selected' : ''}`}
                                onClick={() => setBetPrediction('no')}
                            >
                                <TrendingDown size={24} />
                                <span className="option-label">NO</span>
                                <span className="option-odds">{(100 - selectedMarket.yes_probability * 100).toFixed(0)}%</span>
                            </button>
                        </div>

                        <div className="bet-amount-section">
                            <label>Pick Amount</label>
                            <div className="amount-controls">
                                <button onClick={() => setBetAmount(Math.max(1, betAmount - 5))}>-5</button>
                                <input
                                    type="number"
                                    value={betAmount}
                                    onChange={e => setBetAmount(Math.max(1, Math.min(50, parseInt(e.target.value) || 0)))}
                                    min="1"
                                    max="50"
                                />
                                <button onClick={() => setBetAmount(Math.min(50, betAmount + 5))}>+5</button>
                            </div>
                            <div className="quick-amounts">
                                <button onClick={() => setBetAmount(5)}>5 EP</button>
                                <button onClick={() => setBetAmount(10)}>10 EP</button>
                                <button onClick={() => setBetAmount(25)}>25 EP</button>
                                <button onClick={() => setBetAmount(50)}>MAX</button>
                            </div>
                        </div>

                        {betPrediction && (
                            <div className="payout-preview">
                                <div className="payout-row">
                                    <span>Your pick:</span>
                                    <span>{betAmount} EP on {betPrediction.toUpperCase()}</span>
                                </div>
                                <div className="payout-row highlight">
                                    <span>Potential payout:</span>
                                    <span className="payout-amount">
                                        {calculatePayout(selectedMarket, betPrediction, betAmount)} EP
                                    </span>
                                </div>
                            </div>
                        )}

                        {betError && (
                            <div className="bet-error">
                                <AlertTriangle size={16} />
                                {betError}
                            </div>
                        )}

                        {betSuccess && (
                            <div className="bet-success">
                                <CheckCircle size={16} />
                                {betSuccess}
                            </div>
                        )}

                        <button
                            className="place-bet-btn"
                            onClick={placeBet}
                            disabled={!betPrediction || betAmount < 1 || isPlacingBet || betSuccess}
                        >
                            {isPlacingBet ? (
                                <>
                                    <div className="btn-spinner"></div>
                                    Placing bet...
                                </>
                            ) : (
                                <>
                                    <Coins size={18} />
                                    Make Pick ({betAmount} EP)
                                </>
                            )}
                        </button>

                        <p className="modal-disclaimer">
                            Emergence Points (EP) are virtual currency for fun only. No real money involved.
                        </p>
                    </div>
                </div>
            )}
        </div>
    )
}
