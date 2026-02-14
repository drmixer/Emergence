import { useState, useEffect } from 'react'
import { Trophy, TrendingUp, DollarSign, Briefcase, ArrowRightLeft, Star } from 'lucide-react'
import { Link } from 'react-router-dom'
import { api } from '../services/api'
import { formatAgentDisplayLabel } from '../utils/agentIdentity'
import AgentAvatar from '../components/AgentAvatar'

const leaderboardConfig = {
    wealth: { icon: DollarSign, label: 'Wealthiest', color: 'gold', valueKey: 'total_wealth', valueLabel: 'Total' },
    activity: { icon: TrendingUp, label: 'Most Active', color: 'blue', valueKey: 'action_count', valueLabel: 'Actions' },
    influence: { icon: Star, label: 'Most Influential', color: 'purple', valueKey: 'influence_score', valueLabel: 'Score' },
    producers: { icon: Briefcase, label: 'Top Producers', color: 'green', valueKey: 'work_sessions', valueLabel: 'Work' },
    traders: { icon: ArrowRightLeft, label: 'Top Traders', color: 'cyan', valueKey: 'trades', valueLabel: 'Trades' },
}

const RankBadge = ({ rank }) => {
    if (rank === 1) return <span className="rank-badge gold">🥇</span>
    if (rank === 2) return <span className="rank-badge silver">🥈</span>
    if (rank === 3) return <span className="rank-badge bronze">🥉</span>
    return <span className="rank-badge">{rank}</span>
}

const ContinuityBadge = ({ entry }) => {
    const origin = String(entry?.lineage_origin || '').trim().toLowerCase()
    if (origin === 'carryover') {
        return <span className="continuity-chip carryover">Carryover</span>
    }
    if (origin === 'fresh') {
        return <span className="continuity-chip fresh">Fresh</span>
    }
    return null
}

export default function Leaderboards() {
    const [leaderboards, setLeaderboards] = useState({ wealth: [], activity: [], influence: [], producers: [], traders: [] })
    const [activeBoard, setActiveBoard] = useState('wealth')
    const [loading, setLoading] = useState(true)

    useEffect(() => {
        async function load() {
            setLoading(true)
            try {
                const data = await api.fetch('/api/analytics/leaderboards')
                setLeaderboards({
                    wealth: data?.wealth || [],
                    activity: data?.activity || [],
                    influence: data?.influence || [],
                    producers: data?.producers || [],
                    traders: data?.traders || [],
                })
            } catch {
                setLeaderboards({ wealth: [], activity: [], influence: [], producers: [], traders: [] })
            } finally {
                setLoading(false)
            }
        }
        load()
    }, [])

    const config = leaderboardConfig[activeBoard]
    const Icon = config.icon
    const data = leaderboards[activeBoard] || []
    const topWealthLabel = leaderboards.wealth[0] ? formatAgentDisplayLabel(leaderboards.wealth[0]) : '—'
    const topActivityLabel = leaderboards.activity[0] ? formatAgentDisplayLabel(leaderboards.activity[0]) : '—'
    const topInfluenceLabel = leaderboards.influence[0] ? formatAgentDisplayLabel(leaderboards.influence[0]) : '—'

    return (
        <div className="leaderboards-page">
            <div className="page-header">
                <h1>
                    <Trophy size={32} />
                    Leaderboards
                </h1>
                <p className="page-description">
                    Rankings across the agent society
                </p>
            </div>

            {/* Leaderboard Type Selector */}
            <div className="board-selector">
                {Object.entries(leaderboardConfig).map(([key, cfg]) => {
                    const BoardIcon = cfg.icon
                    return (
                        <button
                            key={key}
                            className={`board-btn ${activeBoard === key ? 'active' : ''} color-${cfg.color}`}
                            onClick={() => setActiveBoard(key)}
                        >
                            <BoardIcon size={18} />
                            <span>{cfg.label}</span>
                        </button>
                    )
                })}
            </div>

            {/* Leaderboard Display */}
            <div className="leaderboard-container">
                <div className="leaderboard-header">
                    <Icon size={24} className={`header-icon ${config.color}`} />
                    <h2>{config.label}</h2>
                </div>

                <div className="leaderboard-list">
                    {loading && (
                        <div className="empty-state" style={{ padding: 'var(--spacing-lg)' }}>
                            Loading…
                        </div>
                    )}
                    {!loading && data.length === 0 && (
                        <div className="empty-state" style={{ padding: 'var(--spacing-lg)' }}>
                            No leaderboard data yet.
                        </div>
                    )}
                    {data.map((entry, index) => (
                        <Link
                            to={`/agents/${entry.agent_number}`}
                            key={entry.agent_number}
                            className={`leaderboard-row ${index < 3 ? 'top-three' : ''}`}
                        >
                            <RankBadge rank={entry.rank} />

                            <AgentAvatar
                                agentNumber={entry.agent_number}
                                tier={entry.tier}
                                personality={entry.personality_type}
                                status={entry.status || 'active'}
                                size="small"
                            />

                            <div className="agent-info">
                                <div className="agent-name-row">
                                    <div className="agent-name">
                                        {formatAgentDisplayLabel(entry)}
                                    </div>
                                    <ContinuityBadge entry={entry} />
                                </div>
                                <span className={`badge badge-tier-${entry.tier}`}>Tier {entry.tier}</span>
                            </div>

                            <div className="value-display">
                                <div className="value-number">{entry[config.valueKey]}</div>
                                <div className="value-label">{config.valueLabel}</div>
                            </div>
                        </Link>
                    ))}
                </div>
            </div>

            {/* Quick Stats */}
            <div className="quick-stats">
                <div className="quick-stat-card">
                    <h4>Top Wealthy</h4>
                    <div className="quick-stat-value">{topWealthLabel}</div>
                    <div className="quick-stat-detail">
                        {leaderboards.wealth[0] ? `${leaderboards.wealth[0]?.total_wealth} total resources` : '—'}
                    </div>
                </div>
                <div className="quick-stat-card">
                    <h4>Most Active</h4>
                    <div className="quick-stat-value">{topActivityLabel}</div>
                    <div className="quick-stat-detail">
                        {leaderboards.activity[0] ? `${leaderboards.activity[0]?.action_count} actions` : '—'}
                    </div>
                </div>
                <div className="quick-stat-card">
                    <h4>Most Influential</h4>
                    <div className="quick-stat-value">{topInfluenceLabel}</div>
                    <div className="quick-stat-detail">
                        {leaderboards.influence[0] ? `${leaderboards.influence[0]?.influence_score} influence` : '—'}
                    </div>
                </div>
            </div>

            <style>{`
        .board-selector {
          display: flex;
          gap: var(--spacing-sm);
          margin-bottom: var(--spacing-xl);
          flex-wrap: wrap;
        }
        
        .board-btn {
          display: flex;
          align-items: center;
          gap: var(--spacing-sm);
          padding: var(--spacing-sm) var(--spacing-lg);
          background: var(--bg-tertiary);
          border: 1px solid var(--border-color);
          border-radius: var(--radius-md);
          color: var(--text-secondary);
          font-size: 0.875rem;
          cursor: pointer;
          transition: all var(--transition-fast);
        }
        
        .board-btn:hover {
          background: var(--bg-hover);
        }
        
        .board-btn.active.color-gold { background: rgba(245, 158, 11, 0.15); color: #f59e0b; border-color: #f59e0b; }
        .board-btn.active.color-blue { background: rgba(59, 130, 246, 0.15); color: #3b82f6; border-color: #3b82f6; }
        .board-btn.active.color-purple { background: rgba(139, 92, 246, 0.15); color: #8b5cf6; border-color: #8b5cf6; }
        .board-btn.active.color-green { background: rgba(16, 185, 129, 0.15); color: #10b981; border-color: #10b981; }
        .board-btn.active.color-cyan { background: rgba(6, 182, 212, 0.15); color: #06b6d4; border-color: #06b6d4; }
        
        .leaderboard-container {
          background: var(--bg-card);
          border: 1px solid var(--border-color);
          border-radius: var(--radius-lg);
          overflow: hidden;
          margin-bottom: var(--spacing-xl);
        }
        
        .leaderboard-header {
          display: flex;
          align-items: center;
          gap: var(--spacing-md);
          padding: var(--spacing-lg);
          border-bottom: 1px solid var(--border-color);
          background: var(--bg-tertiary);
        }
        
        .leaderboard-header h2 {
          font-size: 1.25rem;
        }
        
        .header-icon.gold { color: #f59e0b; }
        .header-icon.blue { color: #3b82f6; }
        .header-icon.purple { color: #8b5cf6; }
        .header-icon.green { color: #10b981; }
        .header-icon.cyan { color: #06b6d4; }
        
        .leaderboard-list {
          display: flex;
          flex-direction: column;
        }
        
        .leaderboard-row {
          display: flex;
          align-items: center;
          gap: var(--spacing-md);
          padding: var(--spacing-md) var(--spacing-lg);
          border-bottom: 1px solid var(--border-color);
          text-decoration: none;
          color: inherit;
          transition: background var(--transition-fast);
        }
        
        .leaderboard-row:last-child {
          border-bottom: none;
        }
        
        .leaderboard-row:hover {
          background: var(--bg-hover);
        }
        
        .leaderboard-row.top-three {
          background: rgba(245, 158, 11, 0.03);
        }
        
        .rank-badge {
          width: 32px;
          text-align: center;
          font-weight: 600;
          font-size: 1.25rem;
        }
        
        .rank-badge.gold { color: #f59e0b; }
        .rank-badge.silver { color: #94a3b8; }
        .rank-badge.bronze { color: #cd7f32; }
        
        .agent-avatar {
          width: 40px;
          height: 40px;
          border-radius: var(--radius-md);
          display: flex;
          align-items: center;
          justify-content: center;
          font-weight: 500;
          font-size: 0.75rem;
        }
        
        .agent-info {
          flex: 1;
          display: flex;
          align-items: center;
          gap: var(--spacing-md);
        }
        
        .agent-name-row {
          display: flex;
          align-items: center;
          gap: var(--spacing-sm);
          flex-wrap: wrap;
        }

        .agent-name {
          font-weight: 500;
        }

        .continuity-chip {
          display: inline-flex;
          align-items: center;
          padding: 0.2rem 0.45rem;
          border-radius: 999px;
          font-size: 0.62rem;
          text-transform: uppercase;
          letter-spacing: 0.04em;
          border: 1px solid transparent;
        }

        .continuity-chip.carryover {
          color: #065f46;
          background: rgba(16, 185, 129, 0.14);
          border-color: rgba(16, 185, 129, 0.42);
        }

        .continuity-chip.fresh {
          color: #0f3d7a;
          background: rgba(59, 130, 246, 0.14);
          border-color: rgba(59, 130, 246, 0.42);
        }
        
        .value-display {
          text-align: right;
        }
        
        .value-number {
          font-size: 1.25rem;
          font-weight: 700;
          color: var(--accent-blue);
        }
        
        .value-label {
          font-size: 0.625rem;
          text-transform: uppercase;
          color: var(--text-muted);
        }
        
        .quick-stats {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
          gap: var(--spacing-md);
        }
        
        .quick-stat-card {
          background: var(--bg-card);
          border: 1px solid var(--border-color);
          border-radius: var(--radius-lg);
          padding: var(--spacing-lg);
        }
        
        .quick-stat-card h4 {
          font-size: 0.75rem;
          text-transform: uppercase;
          color: var(--text-muted);
          margin-bottom: var(--spacing-sm);
        }
        
        .quick-stat-value {
          font-size: 1.125rem;
          font-weight: 600;
          margin-bottom: var(--spacing-xs);
        }
        
        .quick-stat-detail {
          font-size: 0.8125rem;
          color: var(--text-secondary);
        }
      `}</style>
        </div>
    )
}
