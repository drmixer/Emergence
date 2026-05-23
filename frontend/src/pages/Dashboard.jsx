import { startTransition, useEffect, useRef, useState } from 'react'
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
    TrendingUp
} from 'lucide-react'
import { formatDistanceToNow } from 'date-fns'
import { api, subscribeToEvents } from '../services/api'
import ActivityPulse from '../components/ActivityPulse'
import { CriticalAgentsBanner } from '../components/ResourceBar'
import { SkeletonEventCard, SkeletonStatCard, SkeletonTable } from '../components/Skeleton'
import NoActiveRunNotice from '../components/NoActiveRunNotice'
import RunBriefCard from '../components/RunBriefCard'
import { formatAgentDisplayLabel } from '../utils/agentIdentity'
import { getPublicRunFraming } from '../../lib/public-run-framing'
import {
    getCalendarSummaryRuns,
    getRunBriefForArchivedRun,
    getRunBriefForCurrentRun,
} from '../data/runSchedule'

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

function formatNumber(value) {
    return Number(value || 0).toLocaleString()
}

function resourcePercent(current, max) {
    const safeMax = Number(max || 0)
    if (safeMax <= 0) return 0
    return Math.max(0, Math.min(100, (Number(current || 0) / safeMax) * 100))
}

function resourceLevel(percent) {
    if (percent < 20) return 'critical'
    if (percent < 40) return 'low'
    if (percent < 60) return 'watch'
    return 'stable'
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
    const [runMetadata, setRunMetadata] = useState(null)
    const [completedRuns, setCompletedRuns] = useState([])
    const [runArchiveResolved, setRunArchiveResolved] = useState(false)
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

        const applyOverviewAndResources = (overview, resources, archive) => {
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
            setRunMetadata(overview?.run_metadata && typeof overview.run_metadata === 'object' ? overview.run_metadata : null)
            const archiveItems = Array.isArray(archive?.items) ? archive.items : []
            setCompletedRuns(archiveItems.map(getRunBriefForArchivedRun).filter(Boolean))
            setRunArchiveResolved(true)
        }

        const fetchPrimary = async ({ showLoading = false } = {}) => {
            try {
                if (showLoading) {
                    setLoading(true)
                    setError(null)
                }
                const [overview, resources, archive] = await Promise.all([
                    api.getAnalyticsOverview(),
                    api.getResources(),
                    api.getRunsArchive(12, false).catch(() => null),
                ])
                if (cancelled) return
                applyOverviewAndResources(overview, resources, archive)
            } catch (_error) {
                if (cancelled) return
                if (showLoading) {
                    setError('Failed to load live data.')
                    setStats(null)
                    setScope(null)
                    setRunMetadata(null)
                    setCompletedRuns([])
                    setRunArchiveResolved(false)
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
                const [overview, resources, activeProposals, crisisPayload, archive] = await Promise.all([
                    api.getAnalyticsOverview(),
                    api.getResources(),
                    api.fetch('/api/proposals?status=active&limit=5'),
                    api.getCrisisStrip(6),
                    api.getRunsArchive(12, false).catch(() => null),
                ])
                if (cancelled) return

                startTransition(() => {
                    applyOverviewAndResources(overview, resources, archive)
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
    const scopeKnown = !loading && scope !== null
    const scopeResolving = loading || (!error && scope === null)
    const scopeUnavailable = !loading && error && scope === null
    const hasActiveRun = scopeKnown && Boolean(scope?.simulation_active)
    const idleDashboard = scopeKnown && scope?.simulation_active === false
    const liveDashboardVisible = scopeKnown && !idleDashboard
    const lastCompletedRunId = String(scope?.last_completed_run_id || '').trim()
    const latestSocialRow = socialSeries.length > 0 ? socialSeries[socialSeries.length - 1] : null
    const publicOrderLatest = Number(latestSocialRow?.public_order_events || 0)
    const publicOrderDelta = Number(socialDeltas?.public_order_events_delta || 0)
    const conflictDelta = Number(socialDeltas?.conflict_events_delta || 0)
    const allianceDelta = Number(socialDeltas?.alliance_signals_delta || 0)
    const mobility = classMobility?.mobility || {}
    const inequality = classMobility?.inequality || {}
    const publicRunFraming = getPublicRunFraming(runMetadata)
    const activeScheduledRun = hasActiveRun ? getRunBriefForCurrentRun(runMetadata, scope) : null
    const calendarSummary = getCalendarSummaryRuns({
        activeRun: activeScheduledRun,
        completedRuns: runArchiveResolved ? completedRuns : [],
    })
    const nextScheduledRun = runArchiveResolved ? calendarSummary.nextPlanned : null
    const resourceRows = stats ? [
        {
            label: 'Food',
            icon: Apple,
            current: stats.totalFood,
            max: stats.maxFood,
            href: '/resources?focus=food',
            type: 'food',
        },
        {
            label: 'Energy',
            icon: Battery,
            current: stats.totalEnergy,
            max: stats.maxEnergy,
            href: '/resources?focus=energy',
            type: 'energy',
        },
        {
            label: 'Materials',
            icon: Box,
            current: stats.totalMaterials,
            max: stats.maxMaterials,
            href: '/resources?focus=materials',
            type: 'materials',
        },
    ].map((resource) => {
        const percent = resourcePercent(resource.current, resource.max)
        return {
            ...resource,
            percent,
            level: resourceLevel(percent),
        }
    }) : []

    return (
        <div className="dashboard">
            {/* Page Header */}
            <div className="page-header">
                <h1>
                    <Activity size={32} />
                    Run Console
                </h1>
                <p className="page-description">
                    {idleDashboard
                        ? 'Run console is idle. Latest completed run paths and the next declared run are below.'
                        : scopeResolving
                        ? 'Loading current run state before showing live or archived context.'
                        : scopeUnavailable
                        ? 'Current run state is unavailable. No run-specific context is shown until scope loads.'
                        : isPreLaunch
                        ? 'The experiment is about to begin...'
                        : 'Live operational state for the active simulation run.'
                    }
                </p>
            </div>

            {scopeResolving && (
                <div className="card trust-note-card">
                    <div className="card-body trust-note-body">
                        <ShieldCheck size={16} />
                        <p>Resolving the active-run scope before showing run-specific context.</p>
                    </div>
                </div>
            )}

            {liveDashboardVisible && <div className="card trust-note-card">
                <div className="card-body trust-note-body">
                    <ShieldCheck size={16} />
                    <p>
                        Exploratory simulation results. Interpret under this run&apos;s assumptions and verify against run evidence before drawing strong conclusions.
                    </p>
                    <Link to="/method" className="trust-note-link">Method</Link>
                </div>
            </div>}

            {liveDashboardVisible && activeScheduledRun && (
                <RunBriefCard
                    run={activeScheduledRun}
                    variant="compact"
                    heading="Current run brief"
                    actionMode="contextual"
                    analyticsSurface="dashboard_current_run"
                />
            )}

            {liveDashboardVisible && !activeScheduledRun && <div className="card k11-watch-card">
                <div className="card-body k11-watch-body">
                    <div className="k11-watch-intro">
                        <span className="k11-eyebrow">{publicRunFraming.label}</span>
                        <h2>{publicRunFraming.heading}</h2>
                        <p>
                            {publicRunFraming.caveat}
                        </p>
                    </div>
                    <div className="k11-watch-grid" aria-label="What to watch">
                        {publicRunFraming.watchItems.map((signal) => (
                            <div key={signal.label} className="k11-watch-item">
                                <strong>{signal.label}</strong>
                                <span>{signal.detail}</span>
                            </div>
                        ))}
                    </div>
                </div>
            </div>}

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
                <section className="dashboard-idle-console" aria-label="Idle run console">
                    <div className="dashboard-idle-current">
                        <span className="dashboard-section-label">Latest closeout</span>
                        <NoActiveRunNotice
                            title="Console idle"
                            message="No simulation is live. Open the latest completed run in Watch, Replay, Evidence, or the full Archive."
                            lastCompletedRunId={lastCompletedRunId}
                            handoffMode="ops"
                            chrome="inline"
                        />
                    </div>

                    <aside className="dashboard-idle-next" aria-label="Next declared run">
                        <span className="dashboard-section-label">Next declared run</span>
                        {!runArchiveResolved && (
                            <div className="dashboard-idle-resolving">
                                <ShieldCheck size={16} />
                                <p>Resolving archived closeout state before choosing the next scheduled run.</p>
                            </div>
                        )}
                        {runArchiveResolved && nextScheduledRun && (
                            <RunBriefCard
                                run={nextScheduledRun}
                                variant="compact"
                                heading={nextScheduledRun.status === 'Tentative' ? 'Next tentative run' : 'Next scheduled run'}
                                actionMode="calendar"
                                analyticsSurface="dashboard_idle"
                            />
                        )}
                        {runArchiveResolved && !nextScheduledRun && (
                            <div className="dashboard-idle-resolving">
                                <p>No upcoming run is currently declared.</p>
                            </div>
                        )}
                    </aside>
                </section>
            )}

            {!loading && error && (
                <div className="feed-notice">
                    {error}
                </div>
            )}

            {/* Critical Agents Banner */}
            {liveDashboardVisible && !loading && stats && stats.criticalFoodAgents > 0 && (
                <CriticalAgentsBanner count={stats.criticalFoodAgents} type="food" href="/resources?focus=critical-food" />
            )}
            {liveDashboardVisible && !loading && stats && stats.criticalEnergyAgents > 0 && (
                <CriticalAgentsBanner count={stats.criticalEnergyAgents} type="energy" href="/resources?focus=critical-energy" />
            )}

            {/* Crisis Strip */}
            {liveDashboardVisible && !loading && (
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
                                        to={['resource_pressure', 'covered_resource_pressure'].includes(crisis.kind) ? `/resources?focus=critical-${crisis.effect?.resource_type || 'food'}` : `/timeline?event=${encodeURIComponent(crisis.event_id)}`}
                                        className={`crisis-pill ${crisis.kind === 'covered_resource_pressure' ? 'covered' : ''}`}
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

            {liveDashboardVisible && (
                <section className="dashboard-live-console" aria-label="Live operations console">
                    <div className="dashboard-live-main">
                        <div className="dashboard-live-head">
                            <span className="dashboard-section-label">Live state ledger</span>
                            <p>Current run health, pressure, and governance state. Use deeper pages for full lists.</p>
                        </div>

                        {loading ? (
                            <div className="dashboard-live-skeletons">
                                <SkeletonStatCard />
                                <SkeletonStatCard />
                            </div>
                        ) : (
                            <div className="dashboard-live-vitals" aria-label="Live run vital signs">
                                <Link to="/agents?status=active" className="dashboard-live-vital">
                                    <span>
                                        <Users size={16} />
                                        Active
                                    </span>
                                    <strong>{formatNumber(stats?.activeAgents)}</strong>
                                    <em>Agents in the live world</em>
                                </Link>
                                <Link to="/agents?status=dormant" className="dashboard-live-vital attention">
                                    <span>
                                        <AlertTriangle size={16} />
                                        Dormant
                                    </span>
                                    <strong>{formatNumber(stats?.dormantAgents)}</strong>
                                    <em>Agents currently out of play</em>
                                </Link>
                                <Link to="/governance?tab=proposals&status=active" className="dashboard-live-vital">
                                    <span>
                                        <FileText size={16} />
                                        Proposals
                                    </span>
                                    <strong>{formatNumber(stats?.activeProposals)}</strong>
                                    <em>Open governance work</em>
                                </Link>
                                <Link to="/governance?tab=laws" className="dashboard-live-vital">
                                    <span>
                                        <Scale size={16} />
                                        Laws
                                    </span>
                                    <strong>{formatNumber(stats?.passedLaws)}</strong>
                                    <em>Passed in loaded history</em>
                                </Link>
                                <Link to="/timeline" className="dashboard-live-vital">
                                    <span>
                                        <ShieldCheck size={16} />
                                        Public order
                                    </span>
                                    <strong>{formatNumber(publicOrderLatest)}</strong>
                                    <em>Signals in the latest window</em>
                                </Link>
                            </div>
                        )}

                        <div className="dashboard-resource-ledger" aria-label="Resource pressure">
                            <div className="dashboard-ledger-head">
                                <span>Resource pressure</span>
                                <Link to="/resources">Resources</Link>
                            </div>
                            {loading ? (
                                <SkeletonTable rows={3} cols={3} />
                            ) : (
                                <div className="dashboard-resource-list">
                                    {resourceRows.map((resource) => {
                                        const Icon = resource.icon
                                        return (
                                            <Link key={resource.label} to={resource.href} className={`dashboard-resource-row ${resource.level}`}>
                                                <span>
                                                    <Icon size={15} />
                                                    {resource.label}
                                                </span>
                                                <strong>{formatNumber(resource.current)} / {formatNumber(resource.max)}</strong>
                                                <em>{resource.percent.toFixed(0)}%</em>
                                                <div className="dashboard-resource-track" aria-hidden="true">
                                                    <div
                                                        className={`dashboard-resource-fill ${resource.type}`}
                                                        style={{ width: `${resource.percent}%` }}
                                                    />
                                                </div>
                                            </Link>
                                        )
                                    })}
                                </div>
                            )}
                        </div>
                    </div>

                    <div className="dashboard-live-panel" aria-label="Open proposals">
                        <div className="dashboard-panel-head">
                            <div>
                                <span className="dashboard-section-label">Open proposals</span>
                                <p>Governance items still requiring attention.</p>
                            </div>
                            <Link to="/governance?tab=proposals" className="btn btn-secondary">Governance</Link>
                        </div>
                        {loading || secondaryLoading ? (
                            <SkeletonTable rows={3} cols={4} />
                        ) : proposals.length === 0 ? (
                            <div className="empty-state compact">No active proposals right now.</div>
                        ) : (
                            <div className="table-container compact-table-container" tabIndex={0}>
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
                            </div>
                        )}
                    </div>
                </section>
            )}

            {liveDashboardVisible && (
                <section className="dashboard-secondary-ledger" aria-label="Secondary live telemetry">
                    <div className="dashboard-live-panel" aria-label="Activity leaders">
                        <div className="dashboard-panel-head">
                            <div>
                                <span className="dashboard-section-label">Activity leaders</span>
                                <p>Highest action volume in the latest 24 hours.</p>
                            </div>
                            <Link to="/leaderboards" className="btn btn-secondary">Rankings</Link>
                        </div>
                        {loading || secondaryLoading ? (
                            <SkeletonTable rows={5} cols={3} />
                        ) : topAgents.length === 0 ? (
                            <div className="empty-state compact">No activity leaders available yet.</div>
                        ) : (
                            <div className="table-container compact-table-container" tabIndex={0}>
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
                            </div>
                        )}
                    </div>

                    <div className="dashboard-signal-panel" aria-label="Supporting run signals">
                        <div className="dashboard-signal-panel-head">
                            <div>
                                <span className="dashboard-section-label">Supporting signals</span>
                                <p>Lower-priority telemetry stays visible here, with dedicated pages for deeper inspection.</p>
                            </div>
                        </div>

                        <div className="dashboard-signal-grid">
                            <Link to="/archive" className="dashboard-signal-row">
                                <span>
                                    <Flame size={16} />
                                    Plot turns
                                </span>
                                {loading || secondaryLoading ? (
                                    <strong>Loading</strong>
                                ) : plotTurns.length > 0 ? (
                                    <>
                                        <strong>{plotTurns[0].title || 'Latest notable turn'}</strong>
                                        <em>
                                            {plotTurns.length} in 48h
                                            {plotTurns[0].created_at
                                                ? ` · ${formatDistanceToNow(new Date(plotTurns[0].created_at), { addSuffix: true })}`
                                                : ''}
                                        </em>
                                    </>
                                ) : (
                                    <strong>No high-salience turns in 48h</strong>
                                )}
                            </Link>

                            <Link to="/predictions" className="dashboard-signal-row">
                                <span>
                                    <TrendingUp size={16} />
                                    Prediction hooks
                                </span>
                                {loading || secondaryLoading ? (
                                    <strong>Loading</strong>
                                ) : predictionMarkets.length > 0 ? (
                                    <>
                                        <strong>{predictionMarkets.length} open</strong>
                                        <em>{predictionMarkets[0].title}</em>
                                    </>
                                ) : (
                                    <strong>No open prediction hooks</strong>
                                )}
                            </Link>

                            <Link to="/timeline" className="dashboard-signal-row">
                                <span>Social dynamics</span>
                                {loading || secondaryLoading ? (
                                    <strong>Loading</strong>
                                ) : (
                                    <>
                                        <strong>{publicOrderLatest} public-order signals</strong>
                                        <em>
                                            Public order {publicOrderDelta > 0 ? '+' : ''}{publicOrderDelta}
                                            {' · '}Conflict {conflictDelta > 0 ? '+' : ''}{conflictDelta}
                                            {' · '}Alliances {allianceDelta > 0 ? '+' : ''}{allianceDelta}
                                        </em>
                                    </>
                                )}
                            </Link>

                            <Link to="/agents" className="dashboard-signal-row">
                                <span>Class pressure</span>
                                {loading || secondaryLoading ? (
                                    <strong>Loading</strong>
                                ) : !classMobility ? (
                                    <strong>No mobility data yet</strong>
                                ) : (
                                    <>
                                        <strong>Gini {Number(inequality.gini || 0).toFixed(3)}</strong>
                                        <em>
                                            Upward {mobility.upward_signals || 0}
                                            {' · '}Downward {mobility.downward_signals || 0}
                                            {' · '}Flux {formatPct(mobility.signal_flux_rate || 0)}
                                        </em>
                                    </>
                                )}
                            </Link>
                        </div>
                    </div>
                </section>
            )}

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

                .dashboard-live-console {
                    display: grid;
                    grid-template-columns: minmax(0, 1.15fr) minmax(360px, 0.85fr);
                    gap: var(--spacing-xl);
                    margin-bottom: var(--spacing-2xl);
                    padding: var(--spacing-xl) 0;
                    border-top: 1px solid var(--border-color);
                    border-bottom: 1px solid var(--border-color);
                }

                .dashboard-live-main,
                .dashboard-live-panel,
                .dashboard-signal-panel {
                    min-width: 0;
                }

                .dashboard-live-head,
                .dashboard-panel-head {
                    display: flex;
                    justify-content: space-between;
                    gap: var(--spacing-md);
                    align-items: flex-start;
                    margin-bottom: var(--spacing-lg);
                }

                .dashboard-live-head p,
                .dashboard-panel-head p {
                    margin: 0;
                    color: var(--text-secondary);
                    font-size: 0.88rem;
                    line-height: 1.5;
                }

                .dashboard-live-skeletons {
                    display: grid;
                    grid-template-columns: repeat(2, minmax(0, 1fr));
                    gap: var(--spacing-md);
                    margin-bottom: var(--spacing-lg);
                }

                .dashboard-live-vitals {
                    display: grid;
                    grid-template-columns: repeat(5, minmax(0, 1fr));
                    margin-bottom: var(--spacing-xl);
                    border-top: 1px solid var(--border-color);
                    border-bottom: 1px solid var(--border-color);
                }

                .dashboard-live-vital {
                    min-width: 0;
                    display: flex;
                    flex-direction: column;
                    gap: 0.35rem;
                    padding: var(--spacing-md);
                    border-right: 1px solid var(--border-color);
                    color: inherit;
                    text-decoration: none;
                }

                .dashboard-live-vital:last-child {
                    border-right: 0;
                }

                .dashboard-live-vital:hover {
                    background: var(--bg-card-hover);
                }

                .dashboard-live-vital span,
                .dashboard-resource-row span {
                    display: inline-flex;
                    align-items: center;
                    gap: 0.4rem;
                    color: var(--text-muted);
                    font-size: 0.72rem;
                    font-weight: 600;
                    letter-spacing: 0.06em;
                    line-height: 1.35;
                    text-transform: uppercase;
                }

                .dashboard-live-vital strong {
                    color: var(--text-primary);
                    font-size: 1.65rem;
                    line-height: 1.05;
                }

                .dashboard-live-vital em {
                    color: var(--text-secondary);
                    font-size: 0.8rem;
                    font-style: normal;
                    line-height: 1.35;
                }

                .dashboard-live-vital.attention strong {
                    color: var(--accent-orange);
                }

                .dashboard-resource-ledger {
                    min-width: 0;
                }

                .dashboard-ledger-head {
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    gap: var(--spacing-md);
                    margin-bottom: var(--spacing-sm);
                }

                .dashboard-ledger-head span {
                    color: var(--text-muted);
                    font-size: 0.76rem;
                    font-weight: 600;
                    letter-spacing: 0.07em;
                    text-transform: uppercase;
                }

                .dashboard-ledger-head a {
                    color: var(--text-secondary);
                    font-size: 0.82rem;
                    font-weight: 600;
                }

                .dashboard-resource-list {
                    border-top: 1px solid var(--border-color);
                    border-bottom: 1px solid var(--border-color);
                }

                .dashboard-resource-row {
                    min-width: 0;
                    display: grid;
                    grid-template-columns: minmax(120px, 0.8fr) minmax(120px, 0.8fr) 4rem minmax(140px, 1fr);
                    align-items: center;
                    gap: var(--spacing-md);
                    padding: var(--spacing-md) 0;
                    border-bottom: 1px solid var(--border-color);
                    color: inherit;
                    text-decoration: none;
                }

                .dashboard-resource-row:last-child {
                    border-bottom: 0;
                }

                .dashboard-resource-row:hover {
                    background: rgba(255, 255, 255, 0.025);
                }

                .dashboard-resource-row strong {
                    color: var(--text-primary);
                    font-size: 0.94rem;
                }

                .dashboard-resource-row em {
                    color: var(--text-secondary);
                    font-size: 0.82rem;
                    font-style: normal;
                    text-align: right;
                }

                .dashboard-resource-row.critical em,
                .dashboard-resource-row.low em {
                    color: var(--accent-orange);
                }

                .dashboard-resource-track {
                    height: 0.45rem;
                    overflow: hidden;
                    border-radius: var(--radius-full);
                    background: rgba(255, 255, 255, 0.08);
                }

                .dashboard-resource-fill {
                    height: 100%;
                    border-radius: inherit;
                    background: var(--text-muted);
                }

                .dashboard-resource-fill.food {
                    background: var(--accent-green);
                }

                .dashboard-resource-fill.energy {
                    background: #60a5fa;
                }

                .dashboard-resource-fill.materials {
                    background: #c084fc;
                }

                .dashboard-secondary-ledger {
                    display: grid;
                    grid-template-columns: minmax(320px, 0.8fr) minmax(0, 1.2fr);
                    gap: var(--spacing-xl);
                    margin-bottom: var(--spacing-2xl);
                    padding-top: var(--spacing-xl);
                    border-top: 1px solid var(--border-color);
                }

                .dashboard-secondary-ledger .dashboard-signal-panel {
                    margin-bottom: 0;
                    padding-top: 0;
                    border-top: 0;
                }

                .dashboard-secondary-ledger .dashboard-signal-grid {
                    grid-template-columns: repeat(2, minmax(0, 1fr));
                }

                .dashboard-secondary-ledger .dashboard-signal-row:nth-child(2n) {
                    border-right: 0;
                }

                .dashboard-secondary-ledger .dashboard-signal-row:nth-child(n + 3) {
                    border-top: 1px solid var(--border-color);
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

                .crisis-pill.covered {
                    border-color: rgba(59, 130, 246, 0.28);
                    background: rgba(30, 64, 175, 0.16);
                }

                .crisis-pill.covered:hover {
                    border-color: rgba(59, 130, 246, 0.42);
                    background: rgba(30, 64, 175, 0.22);
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

                .k11-watch-card {
                    margin-bottom: var(--spacing-lg);
                    border-color: rgba(245, 158, 11, 0.26);
                    background: linear-gradient(135deg, rgba(245, 158, 11, 0.08), rgba(255, 255, 255, 0.02));
                }

                .k11-watch-body {
                    display: grid;
                    grid-template-columns: minmax(220px, 0.85fr) minmax(0, 1.5fr);
                    gap: var(--spacing-lg);
                    align-items: start;
                }

                .k11-eyebrow {
                    display: inline-block;
                    margin-bottom: var(--spacing-xs);
                    color: #fbbf24;
                    font-size: 0.76rem;
                    font-weight: 700;
                    letter-spacing: 0.12em;
                    text-transform: uppercase;
                }

                .k11-watch-intro h2 {
                    margin: 0 0 var(--spacing-sm);
                    color: var(--text-primary);
                    font-size: 1.35rem;
                }

                .k11-watch-intro p {
                    margin: 0;
                    color: var(--text-secondary);
                    line-height: 1.6;
                }

                .k11-watch-grid {
                    display: grid;
                    grid-template-columns: repeat(5, minmax(0, 1fr));
                    gap: var(--spacing-sm);
                }

                .k11-watch-item {
                    min-height: 112px;
                    padding: var(--spacing-md);
                    border: 1px solid rgba(255, 255, 255, 0.08);
                    border-radius: var(--radius-md);
                    background: rgba(0, 0, 0, 0.16);
                }

                .k11-watch-item strong {
                    display: block;
                    margin-bottom: var(--spacing-xs);
                    color: var(--text-primary);
                    font-size: 0.92rem;
                }

                .k11-watch-item span {
                    color: var(--text-secondary);
                    font-size: 0.82rem;
                    line-height: 1.45;
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

                    .dashboard-live-console,
                    .dashboard-secondary-ledger {
                        grid-template-columns: 1fr;
                    }

                    .dashboard-live-vitals {
                        grid-template-columns: repeat(2, minmax(0, 1fr));
                    }

                    .dashboard-live-vital:nth-child(2n) {
                        border-right: 0;
                    }

                    .dashboard-live-vital:nth-child(n + 3) {
                        border-top: 1px solid var(--border-color);
                    }

                    .dashboard-resource-row {
                        grid-template-columns: minmax(0, 1fr) auto;
                        gap: var(--spacing-sm);
                    }

                    .dashboard-resource-row em {
                        text-align: left;
                    }

                    .dashboard-resource-track {
                        grid-column: 1 / -1;
                    }

                    .dashboard-scope-note {
                        flex-direction: column;
                        align-items: flex-start;
                    }

                    .k11-watch-body {
                        grid-template-columns: 1fr;
                    }

                    .k11-watch-grid {
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
