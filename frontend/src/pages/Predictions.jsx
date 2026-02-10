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

// API base URL
const API_BASE =
    (typeof globalThis !== 'undefined' && globalThis?.process?.env?.NEXT_PUBLIC_API_URL) ||
    ((typeof import.meta !== 'undefined' && import.meta.env?.VITE_API_URL) ? import.meta.env.VITE_API_URL : '') ||
    'http://localhost:8000'

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

// Get or create user ID for identification
const getUserId = () => {
    let userId = localStorage.getItem('emergence_user_id')
    if (!userId) {
        userId = 'user_' + Math.random().toString(36).substring(2, 15)
        localStorage.setItem('emergence_user_id', userId)
    }
    return userId
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

    // Fetch data on mount
    useEffect(() => {
        loadData()
    }, [])

    const loadData = async () => {
        setLoading(true)
        try {
            const [marketsData, leaderboardData, me] = await Promise.all([
                fetchJson('/api/predictions/markets'),
                fetchJson('/api/predictions/leaderboard'),
                fetchJson('/api/predictions/me', { headers: { 'x-user-id': getUserId() } }).catch(() => null),
            ])

            setMarkets(Array.isArray(marketsData) ? marketsData : [])
            setLeaderboard(Array.isArray(leaderboardData) ? leaderboardData : [])
            if (me) setUserStats(me)
        } catch (_error) {
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

    const openBetModal = (market) => {
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
                headers: {
                    'Content-Type': 'application/json',
                    'x-user-id': getUserId()
                },
                body: JSON.stringify({
                    prediction: betPrediction,
                    amount: betAmount
                })
            })

            if (response.ok) {
                setBetSuccess(`Bet placed! ${betAmount} EP on ${betPrediction.toUpperCase()}`)
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
                    Bet Emergence Points (EP) on outcomes. Prove you understand the simulation better than anyone!
                </p>
            </div>

            {/* User Stats Bar */}
            <div className="user-stats-bar">
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
                        <span className="stat-label">Bets Made</span>
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
            </div>

            <div className="predictions-layout">
                {/* Markets Section */}
                <div className="markets-section">
                    {/* Tabs */}
                    <div className="market-tabs">
                        <button
                            className={`tab-btn ${activeTab === 'open' ? 'active' : ''}`}
                            onClick={() => setActiveTab('open')}
                        >
                            <Sparkles size={16} />
                            Open Markets
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
                                <p>No {activeTab} markets found</p>
                            </div>
                        ) : (
                            filteredMarkets.map(market => {
                                const Icon = marketTypeIcons[market.market_type] || Star
                                const isOpen = market.status === 'open'
                                const yesPercent = (market.yes_probability * 100).toFixed(0)
                                const noPercent = (100 - market.yes_probability * 100).toFixed(0)

                                return (
                                    <div
                                        key={market.id}
                                        className={`market-card ${market.status}`}
                                        onClick={() => isOpen && openBetModal(market)}
                                    >
                                        <div className="market-header">
                                            <div className={`market-type-badge ${market.market_type}`}>
                                                <Icon size={14} />
                                                {marketTypeLabels[market.market_type]}
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

                                        <h3 className="market-title">{market.title}</h3>
                                        {market.description && (
                                            <p className="market-description">{market.description}</p>
                                        )}

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
                                                <span>{market.bet_count} bets</span>
                                            </div>
                                            {isOpen && (
                                                <button className="bet-btn">
                                                    Place Bet <ChevronRight size={16} />
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
            {selectedMarket && (
                <div className="modal-overlay" onClick={closeBetModal}>
                    <div className="bet-modal" onClick={e => e.stopPropagation()}>
                        <button className="modal-close" onClick={closeBetModal}>&times;</button>

                        <div className="modal-header">
                            <h2>Place Your Bet</h2>
                            <p className="modal-subtitle">{selectedMarket.title}</p>
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
                            <label>Bet Amount</label>
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
                                    <span>Your bet:</span>
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
                                    Place Bet ({betAmount} EP)
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
