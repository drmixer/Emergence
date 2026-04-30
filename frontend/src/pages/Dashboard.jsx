import { Suspense, lazy, startTransition, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import {
    Users,
    FileText,
    Scale,
    Activity,
    AlertTriangle,
    ShieldCheck,
    Flame,
    Apple,
    Battery,
    Box,
    ArrowUpRight,
    ArrowDownRight,
    Equal,
    TrendingUp
} from 'lucide-react'
import { formatDistanceToNow } from 'date-fns'
import { api, subscribeToEvents } from '../services/api'
import ActivityPulse from '../components/ActivityPulse'
import { ResourceBar, CriticalAgentsBanner } from '../components/ResourceBar'
import { SkeletonEventCard, SkeletonStatCard, SkeletonTable } from '../components/Skeleton'
import NoActiveRunNotice from '../components/NoActiveRunNotice'
import { formatAgentDisplayLabel } from '../utils/agentIdentity'

const DashboardSocialDynamicsChart = lazy(() => import('../components/DashboardSocialDynamicsChart'))

function sumWorldResource(resources, key) {
    const totals = resources?.totals || {}
    const pool = resources?.common_pool || {}
    const a = Number(totals[key] || 0)
    const b = Number(pool[key] || 0)
    return a + b
}

function formatRemaining(seconds) {
    if (seconds === null || seconds === undefined) {
        return 'Live'
    }
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
    const [scope, setScope] = useState(null)
    const [proposals, setProposals] = useState([])
    const [topAgents, setTopAgents] = useState([])
    const [crises, setCrises] = useState([])
    const [plotTurns, setPlotTurns] = useState([])
    const [predictionMarkets, setPredictionMarkets] = useState([])
    const [socialSeries, setSocialSeries] = useState([])
    const [socialDeltas, setSocialDeltas] = useState(null)
    const [classMobility, setClassMobility] = useState(null)
    const [loading, setLoading] = useState(true)
    const [secondaryLoading, setSecondaryLoading] = useState(true)
    const [isLive, setIsLive] = useState(true)
    const [error, setError] = useState(null)
    const refreshTimerRef = useRef(null)

    useEffect(() => {
        let cancelled = false

        const resetSecondaryState = () => {
            setProposals([])
            setTopAgents([])
            setCrises([])
            setPlotTurns([])
            setPredictionMarkets([])
            setSocialSeries([])
            setSocialDeltas(null)
            setClassMobility(null)
        }

        const applyOverviewAndResources = (overview, resources) => {
            setIsLive(Boolean(overview?.scope?.simulation_active))

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
                totalMessages: overview?.messages?.meaningful_total ?? overview?.messages?.total ?? 0,
                degradedFallbackMessages: overview?.messages?.degraded_fallback_total ?? 0,
                dayNumber: overview?.day_number ?? 0,
                lastActivity: overview?.events?.latest ?? null,
                cycleStatus: overview?.cycle_status ?? null,
                criticalFoodAgents: overview?.critical?.food_agents ?? 0,
                criticalEnergyAgents: overview?.critical?.energy_agents ?? 0,
                totalFood: sumWorldResource(resources, 'food'),
                maxFood: foodMax,
                totalEnergy: sumWorldResource(resources, 'energy'),
                maxEnergy: energyMax,
                totalMaterials: sumWorldResource(resources, 'materials'),
                maxMaterials: materialsMax,
            })
            setScope(overview?.scope && typeof overview.scope === 'object' ? overview.scope : null)
        }

        const fetchPrimary = async ({ showLoading = false } = {}) => {
            try {
                if (showLoading) {
                    setLoading(true)
                    setError(null)
                }
                const [overview, resources] = await Promise.all([
                    api.getAnalyticsOverview(),
                    api.getResources(),
                ])
                if (cancelled) return
                applyOverviewAndResources(overview, resources)
            } catch (_error) {
                if (cancelled) return
                if (showLoading) {
                    setError('Failed to load live data.')
                    setStats(null)
                    setScope(null)
                    resetSecondaryState()
                }
            } finally {
                if (showLoading && !cancelled) {
                    setLoading(false)
                }
            }
        }

        const fetchSecondary = async ({ showLoading = false } = {}) => {
            try {
                if (showLoading) {
                    setSecondaryLoading(true)
                }
                const results = await Promise.allSettled([
                    api.fetch('/api/proposals?status=active&limit=5'),
                    api.fetch('/api/analytics/leaderboards/activity?limit=5&hours=24'),
                    api.getCrisisStrip(6),
                    api.getPlotTurns(6, 48, 60),
                    api.getPredictionMarkets('open', 3),
                    api.getSocialDynamics(7),
                    api.getClassMobility(24),
                ])
                if (cancelled) return

                const [
                    activeProposalsResult,
                    activityLeaderboardResult,
                    crisisStripResult,
                    turnsResult,
                    predictionMarketsResult,
                    socialDynamicsResult,
                    mobilityResult,
                ] = results

                startTransition(() => {
                    setProposals(
                        activeProposalsResult.status === 'fulfilled' && Array.isArray(activeProposalsResult.value)
                            ? activeProposalsResult.value
                            : []
                    )
                    setTopAgents(
                        activityLeaderboardResult.status === 'fulfilled' && Array.isArray(activityLeaderboardResult.value)
                            ? activityLeaderboardResult.value
                            : []
                    )
                    setCrises(
                        crisisStripResult.status === 'fulfilled' && Array.isArray(crisisStripResult.value?.items)
                            ? crisisStripResult.value.items
                            : []
                    )
                    setPlotTurns(
                        turnsResult.status === 'fulfilled' && Array.isArray(turnsResult.value?.items)
                            ? turnsResult.value.items
                            : []
                    )
                    setPredictionMarkets(
                        predictionMarketsResult.status === 'fulfilled' && Array.isArray(predictionMarketsResult.value)
                            ? predictionMarketsResult.value
                            : []
                    )
                    setSocialSeries(
                        socialDynamicsResult.status === 'fulfilled' && Array.isArray(socialDynamicsResult.value?.series)
                            ? socialDynamicsResult.value.series
                            : []
                    )
                    setSocialDeltas(
                        socialDynamicsResult.status === 'fulfilled'
                            ? socialDynamicsResult.value?.deltas_vs_prev_day || null
                            : null
                    )
                    setClassMobility(
                        mobilityResult.status === 'fulfilled' && mobilityResult.value && typeof mobilityResult.value === 'object'
                            ? mobilityResult.value
                            : null
                    )
                    if (showLoading) {
                        setSecondaryLoading(false)
                    }
                })
            } catch {
                if (cancelled) return
                startTransition(() => {
                    if (showLoading) {
                        resetSecondaryState()
                        setSecondaryLoading(false)
                    }
                })
            }
        }

        const refreshLiveSnapshot = async () => {
            try {
                const [overview, resources, activeProposals, crisisPayload] = await Promise.all([
                    api.getAnalyticsOverview(),
                    api.getResources(),
                    api.fetch('/api/proposals?status=active&limit=5'),
                    api.getCrisisStrip(6),
                ])
                if (cancelled) return

                startTransition(() => {
                    applyOverviewAndResources(overview, resources)
                    setProposals(Array.isArray(activeProposals) ? activeProposals : [])
                    setCrises(Array.isArray(crisisPayload?.items) ? crisisPayload.items : [])
                })
            } catch {
                // Ignore refresh failures; the mounted data remains usable.
            }
        }

        const scheduleRefresh = () => {
            if (refreshTimerRef.current) {
                return
            }
            refreshTimerRef.current = window.setTimeout(() => {
                refreshTimerRef.current = null
                void refreshLiveSnapshot()
            }, 1500)
        }

        void fetchPrimary({ showLoading: true })
        void fetchSecondary({ showLoading: true })
        const unsubscribe = subscribeToEvents((event) => {
            if (event?.type === 'event') {
                scheduleRefresh()
            }
        })

        return () => {
            cancelled = true
            unsubscribe()
            if (refreshTimerRef.current) {
                window.clearTimeout(refreshTimerRef.current)
                refreshTimerRef.current = null
            }
        }
    }, [])

    // Check for pre-launch state
    const isPreLaunch = stats && stats.dayNumber === 0 && stats.totalMessages === 0
    const hasActiveRun = Boolean(scope?.simulation_active)
    const idleDashboard = !loading && scope?.simulation_active === false
    const lastCompletedRunId = String(scope?.last_completed_run_id || '').trim()
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
                    Current Run
                </h1>
                <p className="page-description">
                    {isPreLaunch
                        ? 'The experiment is about to begin...'
                        : 'Live operational state for the active simulation run.'
                    }
                </p>
            </div>

            <div className="card trust-note-card">
                <div className="card-body trust-note-body">
                    <ShieldCheck size={16} />
                    <p>
                        Exploratory simulation results. Interpret under this run&apos;s assumptions and verify against run evidence before drawing strong conclusions.
                    </p>
                    <Link to="/method" className="trust-note-link">Method</Link>
                </div>
            </div>

            {/* Activity Pulse */}
            {!loading && stats && hasActiveRun && (
                <ActivityPulse
                    isLive={isLive && !isPreLaunch}
                    lastActivity={stats.lastActivity}
                    messageCount={stats.totalMessages}
                    dayNumber={stats.dayNumber}
                    cycleStatus={stats.cycleStatus}
                />
            )}

            {!loading && stats && hasActiveRun && (
                <div className="dashboard-scope-note">
                    <span>{scope?.summary || 'Agent status and resources reflect the live world state. Message, proposal, and law totals are cumulative within the currently loaded simulation database.'}</span>
                    {scope?.active_run_id && (
                        <strong>Run {scope.active_run_id}</strong>
                    )}
                </div>
            )}

            {idleDashboard && (
                <NoActiveRunNotice
                    message="Live metrics will return when the next simulation starts. For now, review completed evidence in the archive."
                    lastCompletedRunId={lastCompletedRunId}
                />
            )}

            {!loading && error && (
                <div className="feed-notice">
                    {error}
                </div>
            )}

            {/* Critical Agents Banner */}
            {!idleDashboard && !loading && stats && stats.criticalFoodAgents > 0 && (
                <CriticalAgentsBanner count={stats.criticalFoodAgents} type="food" href="/resources?focus=critical-food" />
            )}
            {!idleDashboard && !loading && stats && stats.criticalEnergyAgents > 0 && (
                <CriticalAgentsBanner count={stats.criticalEnergyAgents} type="energy" href="/resources?focus=critical-energy" />
            )}

            {/* Crisis Strip */}
            {!idleDashboard && !loading && (
                <div className="card crisis-strip-card">
                    <div className="card-header">
                        <h3>
                            <AlertTriangle size={18} />
                            Crisis Strip
                        </h3>
                        <span className="strip-meta">{secondaryLoading ? 'Loading...' : `${crises.length} active`}</span>
                    </div>
                    <div className="card-body">
                        {secondaryLoading ? (
                            <div className="crisis-skeleton-list">
                                <SkeletonEventCard />
                                <SkeletonEventCard />
                            </div>
                        ) : crises.length === 0 ? (
                            <div className="empty-state compact">No active crises right now.</div>
                        ) : (
                            <div className="crisis-strip-list">
                                {crises.map((crisis) => (
                                    <Link
                                        key={`${crisis.event_id}-${crisis.expires_at}`}
                                        to={crisis.kind === 'resource_pressure' ? `/resources?focus=critical-${crisis.effect?.resource_type || 'food'}` : `/timeline?event=${encodeURIComponent(crisis.event_id)}`}
                                        className="crisis-pill"
                                    >
                                        <div className="crisis-pill-top">
                                            <span className="crisis-name">{crisis.name}</span>
                                            <span className="crisis-timer">{formatRemaining(crisis.seconds_remaining)}</span>
                                        </div>
                                        <div className="crisis-pill-bottom">
                                            <span>{crisis.affected_agents} agents affected</span>
                                        </div>
                                    </Link>
                                ))}
                            </div>
                        )}
                    </div>
                </div>
            )}

            {/* Stats Grid */}
            {!idleDashboard && <div className="stats-grid">
                {loading ? (
                    <>
                        <SkeletonStatCard />
                        <SkeletonStatCard />
                        <SkeletonStatCard />
                        <SkeletonStatCard />
                    </>
                ) : (
                    <>
                        <Link to="/agents?status=active" className="stat-card stat-card-link">
                            <div className="stat-header">
                                <span className="stat-label">Active Agents</span>
                                <div className="stat-icon green">
                                    <Users size={18} />
                                </div>
                            </div>
                            <div className="stat-value">{stats?.activeAgents || 0}</div>
                            <div className="stat-change">
                                <span>Live world state</span>
                            </div>
                        </Link>

                        <Link to="/agents?status=dormant" className="stat-card stat-card-link">
                            <div className="stat-header">
                                <span className="stat-label">Dormant Agents</span>
                                <div className="stat-icon orange">
                                    <AlertTriangle size={18} />
                                </div>
                            </div>
                            <div className="stat-value">{stats?.dormantAgents || 0}</div>
                            <div className="stat-change">
                                <span>Live world state</span>
                            </div>
                        </Link>

                        <Link to="/governance?tab=proposals&status=active" className="stat-card stat-card-link">
                            <div className="stat-header">
                                <span className="stat-label">Active Proposals</span>
                                <div className="stat-icon blue">
                                    <FileText size={18} />
                                </div>
                            </div>
                            <div className="stat-value">{stats?.activeProposals || 0}</div>
                            <div className="stat-change">
                                <span>Open right now</span>
                            </div>
                        </Link>

                        <Link to="/governance?tab=laws" className="stat-card stat-card-link">
                            <div className="stat-header">
                                <span className="stat-label">Passed Laws</span>
                                <div className="stat-icon purple">
                                    <Scale size={18} />
                                </div>
                            </div>
                            <div className="stat-value">{stats?.passedLaws || 0}</div>
                            <div className="stat-change">
                                <span>Cumulative in loaded history</span>
                            </div>
                        </Link>
                    </>
                )}
            </div>}

            {/* Resource Summary with Anxiety Indicators */}
            {!idleDashboard && <div className="resource-grid">
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
            </div>}

            {/* Content Grid */}
            {!idleDashboard && <div className="content-grid">
                {/* Active Proposals */}
                <div className="card">
                    <div className="card-header">
                        <h3>Active Proposals</h3>
                        <Link to="/governance?tab=proposals" className="btn btn-secondary">View All</Link>
                    </div>
                    <div className="card-body">
                        {loading || secondaryLoading ? (
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

                {/* Agent leaderboard snapshot */}
                <div className="card">
                    <div className="card-header">
                        <h3>Agent Leaderboard Snapshot</h3>
                        <Link to="/leaderboards" className="btn btn-secondary">Full Rankings</Link>
                    </div>
                    <div className="card-body">
                        {loading || secondaryLoading ? (
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
            </div>}

            {!idleDashboard && <div className="content-grid">
                <div className="card">
                    <div className="card-header">
                        <h3>
                            <Flame size={18} />
                            Plot Turns
                        </h3>
                        <Link to="/archive" className="btn btn-secondary">Archive</Link>
                    </div>
                    <div className="card-body">
                        {loading || secondaryLoading ? (
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
                        <h3>
                            <TrendingUp size={18} />
                            Prediction Hooks
                        </h3>
                        <Link to="/predictions" className="btn btn-secondary">Open Markets</Link>
                    </div>
                    <div className="card-body">
                        {loading || secondaryLoading ? (
                            <SkeletonTable rows={3} cols={2} />
                        ) : predictionMarkets.length === 0 ? (
                            <div className="empty-state compact">No open prediction hooks for the current run.</div>
                        ) : (
                            <div className="prediction-hook-list">
                                {predictionMarkets.map((market) => (
                                    <Link key={market.id} to="/predictions" className="prediction-hook-item">
                                        <strong>{market.title}</strong>
                                        <span>{market.why_this_matters || market.resolution_basis || 'Resolves from public run evidence.'}</span>
                                    </Link>
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
                        {loading || secondaryLoading ? (
                            <SkeletonTable rows={4} cols={3} />
                        ) : socialChartData.length === 0 ? (
                            <div className="empty-state compact">No social dynamics history yet.</div>
                        ) : (
                            <Suspense fallback={<SkeletonTable rows={4} cols={3} />}>
                                <DashboardSocialDynamicsChart data={socialChartData} />
                            </Suspense>
                        )}
                    </div>
                </div>
            </div>}

            {!idleDashboard && <div className="content-grid">
                <div className="card">
                    <div className="card-header">
                        <h3>Inequality</h3>
                    </div>
                    <div className="card-body inequality-grid">
                        {loading || secondaryLoading ? (
                            <SkeletonTable rows={2} cols={2} />
                        ) : (
                            <>
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
                            </>
                        )}
                    </div>
                </div>

                <div className="card">
                    <div className="card-header">
                        <h3>Class Mobility</h3>
                    </div>
                    <div className="card-body">
                        {loading || secondaryLoading ? (
                            <SkeletonTable rows={3} cols={3} />
                        ) : !classMobility ? (
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
            </div>}

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

                .crisis-skeleton-list {
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
                    gap: var(--spacing-md);
                }

                .crisis-pill {
                    display: block;
                    border: 1px solid rgba(239, 68, 68, 0.28);
                    border-radius: var(--radius-lg);
                    padding: var(--spacing-md);
                    background: rgba(127, 29, 29, 0.18);
                    color: inherit;
                    text-decoration: none;
                }

                .crisis-pill:hover {
                    border-color: rgba(239, 68, 68, 0.42);
                    background: rgba(127, 29, 29, 0.24);
                }

                .stat-card-link {
                    color: inherit;
                    text-decoration: none;
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

                .trust-note-card {
                    margin-bottom: var(--spacing-lg);
                    border-color: rgba(125, 211, 252, 0.28);
                    background: rgba(56, 189, 248, 0.05);
                }

                .trust-note-body {
                    display: flex;
                    align-items: center;
                    gap: var(--spacing-sm);
                    color: var(--text-secondary);
                    font-size: 0.9rem;
                    padding-top: var(--spacing-md);
                    padding-bottom: var(--spacing-md);
                }

                .trust-note-body p {
                    flex: 1;
                    margin: 0;
                }

                .trust-note-link {
                    color: #7dd3fc;
                    font-weight: 600;
                }

                .trust-note-link:hover {
                    color: #bae6fd;
                }

                .dashboard-scope-note {
                    margin-bottom: var(--spacing-lg);
                    display: flex;
                    justify-content: space-between;
                    gap: var(--spacing-md);
                    align-items: center;
                    padding: var(--spacing-sm) var(--spacing-md);
                    border: 1px solid rgba(255, 255, 255, 0.08);
                    border-radius: var(--radius-md);
                    background: rgba(255, 255, 255, 0.02);
                    color: var(--text-secondary);
                    font-size: 0.83rem;
                }

                .dashboard-scope-note strong {
                    color: var(--text-primary);
                    font-size: 0.78rem;
                    white-space: nowrap;
                }
                
                @media (max-width: 768px) {
                    .resource-grid {
                        grid-template-columns: 1fr;
                    }

                    .inequality-grid {
                        grid-template-columns: 1fr;
                    }

                    .dashboard-scope-note {
                        flex-direction: column;
                        align-items: flex-start;
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
