import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import {
    Users,
    FileText,
    Scale,
    TrendingUp,
    TrendingDown,
    Activity,
    AlertTriangle,
    Flame,
    Apple,
    Battery,
    Box,
    ArrowUpRight,
    ArrowDownRight,
    Equal
} from 'lucide-react'
import { formatDistanceToNow } from 'date-fns'
import {
    ResponsiveContainer,
    LineChart,
    Line,
    CartesianGrid,
    XAxis,
    YAxis,
    Tooltip,
    Legend
} from 'recharts'
import { api } from '../services/api'
import ActivityPulse from '../components/ActivityPulse'
import { ResourceBar, CriticalAgentsBanner } from '../components/ResourceBar'
import { SkeletonStatCard, SkeletonTable } from '../components/Skeleton'
import { formatAgentDisplayLabel } from '../utils/agentIdentity'

function sumWorldResource(resources, key) {
    const totals = resources?.totals || {}
    const pool = resources?.common_pool || {}
    const a = Number(totals[key] || 0)
    const b = Number(pool[key] || 0)
    return a + b
}

function formatRemaining(seconds) {
    const safe = Math.max(0, Number(seconds || 0))
    const hours = Math.floor(safe / 3600)
    const minutes = Math.floor((safe % 3600) / 60)
    if (hours > 0) {
        return `${hours}h ${minutes}m`
    }
    return `${minutes}m`
}

function formatPct(value) {
    return `${(Number(value || 0) * 100).toFixed(1)}%`
}

export default function Dashboard() {
    const [stats, setStats] = useState(null)
    const [proposals, setProposals] = useState([])
    const [topAgents, setTopAgents] = useState([])
    const [crises, setCrises] = useState([])
    const [plotTurns, setPlotTurns] = useState([])
    const [socialSeries, setSocialSeries] = useState([])
    const [socialDeltas, setSocialDeltas] = useState(null)
    const [classMobility, setClassMobility] = useState(null)
    const [loading, setLoading] = useState(true)
    const [isLive, setIsLive] = useState(true)
    const [error, setError] = useState(null)

    useEffect(() => {
        const fetchData = async () => {
            try {
                setError(null)
                const [overview, resources, activeProposals, activityLeaderboard, crisisStrip, turns, socialDynamics, mobility] = await Promise.all([
                    api.getAnalyticsOverview(),
                    api.getResources(),
                    api.fetch('/api/proposals?status=active&limit=5'),
                    api.fetch('/api/analytics/leaderboards/activity?limit=5&hours=24'),
                    api.getCrisisStrip(6).catch(() => ({ items: [] })),
                    api.getPlotTurns(6, 48, 60).catch(() => ({ items: [] })),
                    api.getSocialDynamics(7).catch(() => ({ series: [], deltas_vs_prev_day: null })),
                    api.getClassMobility(24).catch(() => null),
                ])

                setIsLive(Boolean(overview?.events?.latest))

                const capacity = overview?.resources?.capacity_estimate || {}
                const foodMax = Number(capacity.food || 0) || 1
                const energyMax = Number(capacity.energy || 0) || 1
                const materialsMax = Number(capacity.materials || 0) || 1

                setStats({
                    activeAgents: overview?.agents?.active ?? 0,
                    dormantAgents: overview?.agents?.dormant ?? 0,
                    deadAgents: overview?.agents?.dead ?? 0,
                    activeProposals: overview?.proposals?.active ?? 0,
                    passedLaws: overview?.laws?.total ?? 0,
                    totalMessages: overview?.messages?.total ?? 0,
                    dayNumber: overview?.day_number ?? 0,
                    lastActivity: overview?.events?.latest ?? null,
                    criticalFoodAgents: overview?.critical?.food_agents ?? 0,
                    criticalEnergyAgents: overview?.critical?.energy_agents ?? 0,
                    totalFood: sumWorldResource(resources, 'food'),
                    maxFood: foodMax,
                    totalEnergy: sumWorldResource(resources, 'energy'),
                    maxEnergy: energyMax,
                    totalMaterials: sumWorldResource(resources, 'materials'),
                    maxMaterials: materialsMax,
                })

                setProposals(Array.isArray(activeProposals) ? activeProposals : [])
                setTopAgents(Array.isArray(activityLeaderboard) ? activityLeaderboard : [])
                setCrises(Array.isArray(crisisStrip?.items) ? crisisStrip.items : [])
                setPlotTurns(Array.isArray(turns?.items) ? turns.items : [])
                setSocialSeries(Array.isArray(socialDynamics?.series) ? socialDynamics.series : [])
                setSocialDeltas(socialDynamics?.deltas_vs_prev_day || null)
                setClassMobility(mobility && typeof mobility === 'object' ? mobility : null)
            } catch (_error) {
                setError('Failed to load live data.')
                setStats(null)
                setProposals([])
                setTopAgents([])
                setCrises([])
                setPlotTurns([])
                setSocialSeries([])
                setSocialDeltas(null)
                setClassMobility(null)
            } finally {
                setLoading(false)
            }
        }

        fetchData()
    }, [])

    // Check for pre-launch state
    const isPreLaunch = stats && stats.dayNumber === 0 && stats.totalMessages === 0
    const socialChartData = socialSeries.map((row) => ({
        day: row.day_label,
        conflict: Number(row.conflict_events || 0),
        cooperation: Number(row.cooperation_events || 0),
        alliances: Number(row.alliance_signals || 0),
    }))
    const tiers = Array.isArray(classMobility?.tiers) ? classMobility.tiers : []
    const mobility = classMobility?.mobility || {}
    const inequality = classMobility?.inequality || {}

    return (
        <div className="dashboard">
            {/* Page Header */}
            <div className="page-header">
                <h1>
                    <Activity size={32} />
                    Dashboard
                </h1>
                <p className="page-description">
                    {isPreLaunch
                        ? 'The experiment is about to begin...'
                        : 'Overview of the AI civilization experiment'
                    }
                </p>
            </div>

            {/* Activity Pulse */}
            {!loading && stats && (
                <ActivityPulse
                    isLive={isLive && !isPreLaunch}
                    lastActivity={stats.lastActivity}
                    messageCount={stats.totalMessages}
                    dayNumber={stats.dayNumber}
                />
            )}

            {!loading && error && (
                <div className="feed-notice">
                    {error}
                </div>
            )}

            {/* Critical Agents Banner */}
            {!loading && stats && stats.criticalFoodAgents > 0 && (
                <CriticalAgentsBanner count={stats.criticalFoodAgents} type="food" />
            )}

            {/* Crisis Strip */}
            {!loading && (
                <div className="card crisis-strip-card">
                    <div className="card-header">
                        <h3>
                            <AlertTriangle size={18} />
                            Crisis Strip
                        </h3>
                        <span className="strip-meta">{crises.length} active</span>
                    </div>
                    <div className="card-body">
                        {crises.length === 0 ? (
                            <div className="empty-state compact">No active crises right now.</div>
                        ) : (
                            <div className="crisis-strip-list">
                                {crises.map((crisis) => (
                                    <div key={`${crisis.event_id}-${crisis.expires_at}`} className="crisis-pill">
                                        <div className="crisis-pill-top">
                                            <span className="crisis-name">{crisis.name}</span>
                                            <span className="crisis-timer">{formatRemaining(crisis.seconds_remaining)}</span>
                                        </div>
                                        <div className="crisis-pill-bottom">
                                            <span>{crisis.affected_agents} agents affected</span>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                </div>
            )}

            {/* Stats Grid */}
            <div className="stats-grid">
                {loading ? (
                    <>
                        <SkeletonStatCard />
                        <SkeletonStatCard />
                        <SkeletonStatCard />
                        <SkeletonStatCard />
                    </>
                ) : (
                    <>
                        <div className="stat-card">
                            <div className="stat-header">
                                <span className="stat-label">Active Agents</span>
                                <div className="stat-icon green">
                                    <Users size={18} />
                                </div>
                            </div>
                            <div className="stat-value">{stats?.activeAgents || 0}</div>
                            <div className="stat-change positive">
                                <TrendingUp size={14} />
                                <span>+2 from yesterday</span>
                            </div>
                        </div>

                        <div className="stat-card">
                            <div className="stat-header">
                                <span className="stat-label">Dormant Agents</span>
                                <div className="stat-icon orange">
                                    <AlertTriangle size={18} />
                                </div>
                            </div>
                            <div className="stat-value">{stats?.dormantAgents || 0}</div>
                            <div className="stat-change negative">
                                <TrendingDown size={14} />
                                <span>-2 from yesterday</span>
                            </div>
                        </div>

                        <div className="stat-card">
                            <div className="stat-header">
                                <span className="stat-label">Active Proposals</span>
                                <div className="stat-icon blue">
                                    <FileText size={18} />
                                </div>
                            </div>
                            <div className="stat-value">{stats?.activeProposals || 0}</div>
                        </div>

                        <div className="stat-card">
                            <div className="stat-header">
                                <span className="stat-label">Passed Laws</span>
                                <div className="stat-icon purple">
                                    <Scale size={18} />
                                </div>
                            </div>
                            <div className="stat-value">{stats?.passedLaws || 0}</div>
                        </div>
                    </>
                )}
            </div>

            {/* Resource Summary with Anxiety Indicators */}
            <div className="resource-grid">
                {loading ? (
                    <>
                        <SkeletonStatCard />
                        <SkeletonStatCard />
                        <SkeletonStatCard />
                    </>
                ) : (
                    <>
                        <ResourceBar
                            label="Total Food"
                            icon={Apple}
                            current={stats?.totalFood || 0}
                            max={stats?.maxFood || 5000}
                            type="food"
                        />
                        <ResourceBar
                            label="Total Energy"
                            icon={Battery}
                            current={stats?.totalEnergy || 0}
                            max={stats?.maxEnergy || 4000}
                            type="energy"
                        />
                        <ResourceBar
                            label="Total Materials"
                            icon={Box}
                            current={stats?.totalMaterials || 0}
                            max={stats?.maxMaterials || 2000}
                            type="materials"
                        />
                    </>
                )}
            </div>

            {/* Content Grid */}
            <div className="content-grid">
                {/* Active Proposals */}
                <div className="card">
                    <div className="card-header">
                        <h3>Active Proposals</h3>
                        <Link to="/proposals" className="btn btn-secondary">View All</Link>
                    </div>
                    <div className="card-body">
                        {loading ? (
                            <SkeletonTable rows={3} cols={4} />
                        ) : (
                            <table>
                                <thead>
                                    <tr>
                                        <th>Proposal</th>
                                        <th>Author</th>
                                        <th>Votes</th>
                                        <th>Status</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {proposals.map(proposal => (
                                        <tr key={proposal.id}>
                                            <td>{proposal.title}</td>
                                            <td>
                                                {proposal.author
                                                    ? formatAgentDisplayLabel(proposal.author)
                                                    : 'Unknown'}
                                            </td>
                                            <td>
                                                <span style={{ color: 'var(--accent-green)' }}>{proposal.votes_for}</span>
                                                {' / '}
                                                <span style={{ color: 'var(--accent-red)' }}>{proposal.votes_against}</span>
                                            </td>
                                            <td>
                                                <span className={`badge badge-${proposal.status === 'active' ? 'active' : 'passed'}`}>
                                                    {proposal.status}
                                                </span>
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        )}
                    </div>
                </div>

                {/* Most Active Agents */}
                <div className="card">
                    <div className="card-header">
                        <h3>Most Active Agents</h3>
                        <Link to="/agents" className="btn btn-secondary">View All</Link>
                    </div>
                    <div className="card-body">
                        {loading ? (
                            <SkeletonTable rows={5} cols={4} />
                        ) : (
                            <table>
                                <thead>
                                    <tr>
                                        <th>Agent</th>
                                        <th>Tier</th>
                                        <th>Actions (24h)</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {topAgents.map(agent => (
                                        <tr key={agent.agent_id}>
                                            <td>
                                                <Link to={`/agents/${agent.agent_number}`}>
                                                    {formatAgentDisplayLabel(agent)}
                                                </Link>
                                            </td>
                                            <td>
                                                <span className={`badge badge-tier-${agent.tier}`}>
                                                    Tier {agent.tier}
                                                </span>
                                            </td>
                                            <td>{agent.action_count}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        )}
                    </div>
                </div>
            </div>

            <div className="content-grid">
                <div className="card">
                    <div className="card-header">
                        <h3>
                            <Flame size={18} />
                            Plot Turns
                        </h3>
                        <Link to="/highlights" className="btn btn-secondary">Highlights</Link>
                    </div>
                    <div className="card-body">
                        {loading ? (
                            <SkeletonTable rows={4} cols={3} />
                        ) : plotTurns.length === 0 ? (
                            <div className="empty-state compact">No high-salience turns in the last 48h.</div>
                        ) : (
                            <div className="plot-turn-list">
                                {plotTurns.map((turn) => (
                                    <div key={turn.event_id} className={`plot-turn-item category-${turn.category || 'notable'}`}>
                                        <div className="plot-turn-head">
                                            <span className="plot-turn-title">{turn.title}</span>
                                            <span className="plot-turn-score">{turn.salience}</span>
                                        </div>
                                        <p className="plot-turn-description">{turn.description}</p>
                                        <div className="plot-turn-foot">
                                            <span className="plot-turn-category">{(turn.category || 'notable').replace(/_/g, ' ')}</span>
                                            <span className="plot-turn-time">
                                                {turn.created_at
                                                    ? formatDistanceToNow(new Date(turn.created_at), { addSuffix: true })
                                                    : ''}
                                            </span>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                </div>

                <div className="card">
                    <div className="card-header">
                        <h3>Social Dynamics (7d)</h3>
                        {socialDeltas && (
                            <div className="deltas-inline">
                                <span className={socialDeltas.conflict_events_delta > 0 ? 'delta-up' : 'delta-down'}>
                                    Conflict {socialDeltas.conflict_events_delta > 0 ? '+' : ''}{socialDeltas.conflict_events_delta}
                                </span>
                                <span className={socialDeltas.alliance_signals_delta >= 0 ? 'delta-up' : 'delta-down'}>
                                    Alliances {socialDeltas.alliance_signals_delta > 0 ? '+' : ''}{socialDeltas.alliance_signals_delta}
                                </span>
                            </div>
                        )}
                    </div>
                    <div className="card-body social-body">
                        {socialChartData.length === 0 ? (
                            <div className="empty-state compact">No social dynamics history yet.</div>
                        ) : (
                            <ResponsiveContainer width="100%" height={240}>
                                <LineChart data={socialChartData} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
                                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.08)" />
                                    <XAxis dataKey="day" stroke="rgba(255,255,255,0.55)" />
                                    <YAxis allowDecimals={false} stroke="rgba(255,255,255,0.55)" />
                                    <Tooltip
                                        contentStyle={{
                                            background: 'rgba(8, 10, 18, 0.96)',
                                            border: '1px solid rgba(255,255,255,0.12)',
                                            borderRadius: '8px',
                                        }}
                                    />
                                    <Legend />
                                    <Line type="monotone" dataKey="conflict" name="Conflict" stroke="#ef4444" strokeWidth={2} dot={false} />
                                    <Line type="monotone" dataKey="cooperation" name="Cooperation" stroke="#22c55e" strokeWidth={2} dot={false} />
                                    <Line type="monotone" dataKey="alliances" name="Alliances" stroke="#60a5fa" strokeWidth={2} dot={false} />
                                </LineChart>
                            </ResponsiveContainer>
                        )}
                    </div>
                </div>
            </div>

            <div className="content-grid">
                <div className="card">
                    <div className="card-header">
                        <h3>Inequality</h3>
                    </div>
                    <div className="card-body inequality-grid">
                        <div className="inequality-main">
                            <div className="inequality-value">{Number(inequality.gini || 0).toFixed(3)}</div>
                            <div className="inequality-label">Gini coefficient</div>
                        </div>
                        <div className="inequality-stats">
                            <div><span>P25</span><strong>{Number(inequality.p25 || 0).toFixed(1)}</strong></div>
                            <div><span>Median</span><strong>{Number(inequality.median || 0).toFixed(1)}</strong></div>
                            <div><span>P75</span><strong>{Number(inequality.p75 || 0).toFixed(1)}</strong></div>
                            <div>
                                <span>Trend</span>
                                <strong className={(inequality.trend || 0) > 0 ? 'delta-up' : 'delta-down'}>
                                    {(Number(inequality.trend || 0) > 0 ? '+' : '') + Number(inequality.trend || 0).toFixed(3)}
                                </strong>
                            </div>
                        </div>
                    </div>
                </div>

                <div className="card">
                    <div className="card-header">
                        <h3>Class Mobility</h3>
                    </div>
                    <div className="card-body">
                        {!classMobility ? (
                            <div className="empty-state compact">No mobility data yet.</div>
                        ) : (
                            <>
                                <div className="mobility-signals">
                                    <div className="mobility-chip up">
                                        <ArrowUpRight size={16} />
                                        Upward {mobility.upward_signals || 0}
                                    </div>
                                    <div className="mobility-chip down">
                                        <ArrowDownRight size={16} />
                                        Downward {mobility.downward_signals || 0}
                                    </div>
                                    <div className="mobility-chip neutral">
                                        <Equal size={16} />
                                        Flux {formatPct(mobility.signal_flux_rate || 0)}
                                    </div>
                                </div>
                                <div className="tier-wealth-list">
                                    {tiers.map((tier) => (
                                        <div key={tier.tier} className="tier-wealth-row">
                                            <div className="tier-label">Tier {tier.tier}</div>
                                            <div className="tier-bar-wrap">
                                                <div
                                                    className="tier-bar-fill"
                                                    style={{ width: `${Math.max(4, Math.round(Number(tier.wealth_share || 0) * 100))}%` }}
                                                />
                                            </div>
                                            <div className="tier-value">{formatPct(tier.wealth_share || 0)}</div>
                                        </div>
                                    ))}
                                </div>
                            </>
                        )}
                    </div>
                </div>
            </div>

            <style>{`
                .resource-grid {
                    display: grid;
                    grid-template-columns: repeat(3, 1fr);
                    gap: var(--spacing-lg);
                    margin-bottom: var(--spacing-xl);
                }

                .crisis-strip-card {
                    margin-bottom: var(--spacing-xl);
                }

                .strip-meta {
                    font-size: 0.8rem;
                    color: var(--text-muted);
                }

                .crisis-strip-list {
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
                    gap: var(--spacing-md);
                }

                .crisis-pill {
                    border: 1px solid rgba(239, 68, 68, 0.28);
                    border-radius: var(--radius-lg);
                    padding: var(--spacing-md);
                    background: rgba(127, 29, 29, 0.18);
                }

                .crisis-pill-top {
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    gap: var(--spacing-sm);
                }

                .crisis-name {
                    font-weight: 600;
                }

                .crisis-timer {
                    font-size: 0.85rem;
                    color: #fca5a5;
                }

                .crisis-pill-bottom {
                    margin-top: var(--spacing-xs);
                    color: var(--text-secondary);
                    font-size: 0.85rem;
                }

                .plot-turn-list {
                    display: flex;
                    flex-direction: column;
                    gap: var(--spacing-sm);
                }

                .plot-turn-item {
                    border: 1px solid rgba(255, 255, 255, 0.08);
                    border-left-width: 4px;
                    border-radius: var(--radius-md);
                    padding: var(--spacing-md);
                    background: rgba(255, 255, 255, 0.02);
                }

                .plot-turn-item.category-crisis { border-left-color: #f97316; }
                .plot-turn-item.category-conflict { border-left-color: #ef4444; }
                .plot-turn-item.category-alliance { border-left-color: #3b82f6; }
                .plot-turn-item.category-governance { border-left-color: #a78bfa; }
                .plot-turn-item.category-cooperation { border-left-color: #22c55e; }
                .plot-turn-item.category-notable { border-left-color: #94a3b8; }

                .plot-turn-head {
                    display: flex;
                    justify-content: space-between;
                    gap: var(--spacing-sm);
                    align-items: baseline;
                }

                .plot-turn-title {
                    font-weight: 600;
                }

                .plot-turn-score {
                    font-size: 0.8rem;
                    color: var(--text-muted);
                }

                .plot-turn-description {
                    margin: var(--spacing-xs) 0;
                    color: var(--text-secondary);
                    font-size: 0.9rem;
                }

                .plot-turn-foot {
                    display: flex;
                    justify-content: space-between;
                    gap: var(--spacing-sm);
                    font-size: 0.78rem;
                    color: var(--text-muted);
                    text-transform: capitalize;
                }

                .deltas-inline {
                    display: inline-flex;
                    gap: var(--spacing-sm);
                    font-size: 0.78rem;
                }

                .social-body {
                    min-height: 260px;
                }

                .inequality-grid {
                    display: grid;
                    grid-template-columns: 180px 1fr;
                    gap: var(--spacing-lg);
                }

                .inequality-main {
                    display: flex;
                    flex-direction: column;
                    justify-content: center;
                    align-items: center;
                    border: 1px solid rgba(255, 255, 255, 0.08);
                    border-radius: var(--radius-lg);
                    padding: var(--spacing-md);
                }

                .inequality-value {
                    font-size: 2rem;
                    font-weight: 700;
                }

                .inequality-label {
                    color: var(--text-muted);
                    font-size: 0.8rem;
                }

                .inequality-stats {
                    display: grid;
                    grid-template-columns: repeat(2, minmax(0, 1fr));
                    gap: var(--spacing-sm);
                }

                .inequality-stats div {
                    border: 1px solid rgba(255, 255, 255, 0.08);
                    border-radius: var(--radius-md);
                    padding: var(--spacing-sm);
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    gap: var(--spacing-sm);
                    font-size: 0.85rem;
                }

                .mobility-signals {
                    display: flex;
                    flex-wrap: wrap;
                    gap: var(--spacing-sm);
                    margin-bottom: var(--spacing-md);
                }

                .mobility-chip {
                    display: inline-flex;
                    align-items: center;
                    gap: 0.3rem;
                    padding: 0.3rem 0.55rem;
                    border-radius: 999px;
                    border: 1px solid rgba(255, 255, 255, 0.12);
                    font-size: 0.78rem;
                }

                .mobility-chip.up { color: #86efac; border-color: rgba(34, 197, 94, 0.3); }
                .mobility-chip.down { color: #fca5a5; border-color: rgba(239, 68, 68, 0.3); }
                .mobility-chip.neutral { color: #bfdbfe; border-color: rgba(59, 130, 246, 0.3); }

                .tier-wealth-list {
                    display: flex;
                    flex-direction: column;
                    gap: var(--spacing-sm);
                }

                .tier-wealth-row {
                    display: grid;
                    grid-template-columns: 56px 1fr 64px;
                    gap: var(--spacing-sm);
                    align-items: center;
                }

                .tier-label {
                    font-size: 0.8rem;
                    color: var(--text-muted);
                }

                .tier-bar-wrap {
                    height: 8px;
                    border-radius: 999px;
                    background: rgba(255, 255, 255, 0.08);
                    overflow: hidden;
                }

                .tier-bar-fill {
                    height: 100%;
                    background: linear-gradient(90deg, #60a5fa, #c084fc);
                }

                .tier-value {
                    text-align: right;
                    font-size: 0.8rem;
                    color: var(--text-secondary);
                }

                .delta-up {
                    color: #86efac;
                }

                .delta-down {
                    color: #fca5a5;
                }

                .empty-state.compact {
                    min-height: 0;
                    padding: var(--spacing-md);
                    border: 1px dashed rgba(255, 255, 255, 0.12);
                    border-radius: var(--radius-md);
                    color: var(--text-muted);
                }
                
                @media (max-width: 768px) {
                    .resource-grid {
                        grid-template-columns: 1fr;
                    }

                    .inequality-grid {
                        grid-template-columns: 1fr;
                    }
                }
                
                .badge-passed {
                    background: rgba(16, 185, 129, 0.15);
                    color: var(--accent-green);
                }
            `}</style>
        </div>
    )
}
