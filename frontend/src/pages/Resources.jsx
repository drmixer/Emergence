import { Suspense, lazy, useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Package, TrendingUp, TrendingDown } from 'lucide-react'
import { api } from '../services/api'
import { formatAgentDisplayLabel } from '../utils/agentIdentity'

const ResourcesCharts = lazy(() => import('../components/ResourcesCharts'))

const COLORS = {
    tier1: '#f59e0b',
    tier2: '#8b5cf6',
    tier3: '#3b82f6',
    tier4: '#6b7280',
}

function formatNumber(n) {
    if (n === null || n === undefined || Number.isNaN(Number(n))) return '—'
    return Number(n).toLocaleString(undefined, { maximumFractionDigits: 2 })
}

export default function Resources() {
    const [searchParams] = useSearchParams()
    const [loading, setLoading] = useState(true)
    const [secondaryLoading, setSecondaryLoading] = useState(true)
    const [error, setError] = useState(null)
    const [resources, setResources] = useState(null)
    const [history, setHistory] = useState(null)
    const [distribution, setDistribution] = useState(null)
    const [agents, setAgents] = useState([])
    const [aidLifecycle, setAidLifecycle] = useState(null)

    useEffect(() => {
        let cancelled = false

        async function load() {
            setLoading(true)
            setSecondaryLoading(true)
            setError(null)
            try {
                const res = await api.getResources()
                if (cancelled) return
                setResources(res)
            } catch (e) {
                if (cancelled) return
                setError(e)
            } finally {
                if (!cancelled) {
                    setLoading(false)
                }
            }

            try {
                const [hist, dist, agentList, aid] = await Promise.all([
                    api.getResourceHistory(),
                    api.getResourceDistribution(),
                    api.getAgents(),
                    api.getAidLifecycle(80),
                ])
                if (cancelled) return
                setHistory(hist)
                setDistribution(dist)
                setAgents(Array.isArray(agentList) ? agentList : [])
                setAidLifecycle(aid && typeof aid === 'object' ? aid : null)
            } catch {
                if (cancelled) return
                setHistory(null)
                setDistribution(null)
                setAgents([])
                setAidLifecycle(null)
            } finally {
                if (!cancelled) {
                    setSecondaryLoading(false)
                }
            }
        }
        load()
        return () => {
            cancelled = true
        }
    }, [])

    const totals = resources?.totals || {}
    const focus = String(searchParams.get('focus') || '').trim()

    const dailyNet = useMemo(() => {
        const series = history?.series
        if (!Array.isArray(series) || series.length === 0) return {}

        const latestByResource = new Map()
        for (const row of series) {
            if (!row?.resource_type) continue
            if (!['food', 'energy', 'materials'].includes(row.resource_type)) continue
            const prev = latestByResource.get(row.resource_type)
            if (!prev || String(row.day) > String(prev.day)) {
                latestByResource.set(row.resource_type, row)
            }
        }

        return {
            food: latestByResource.get('food')?.net ?? 0,
            energy: latestByResource.get('energy')?.net ?? 0,
            materials: latestByResource.get('materials')?.net ?? 0,
        }
    }, [history])

    const historyChartData = useMemo(() => {
        const series = history?.series
        if (!Array.isArray(series) || series.length === 0) return []

        const byDay = new Map()
        for (const row of series) {
            if (!row?.day || !row?.resource_type) continue
            if (!['food', 'energy', 'materials'].includes(row.resource_type)) continue
            const key = String(row.day)
            const existing = byDay.get(key) || { day: key, food: 0, energy: 0, materials: 0 }
            existing[row.resource_type] = Number(row.net ?? 0)
            byDay.set(key, existing)
        }
        return Array.from(byDay.values()).sort((a, b) => String(a.day).localeCompare(String(b.day)))
    }, [history])

    const distributionByTier = useMemo(() => {
        const dist = distribution?.distribution
        if (!Array.isArray(dist) || dist.length === 0) return []

        const tierByAgentNumber = new Map()
        for (const a of agents) {
            tierByAgentNumber.set(Number(a.agent_number), Number(a.tier))
        }

        const sums = new Map()
        for (const row of dist) {
            const agentNum = Number(row.agent_number)
            const tier = tierByAgentNumber.get(agentNum)
            if (!tier) continue

            const bucket = sums.get(tier) || { tier, food: 0, energy: 0, materials: 0, total: 0 }
            const r = row.resources || {}
            bucket.food += Number(r.food ?? 0)
            bucket.energy += Number(r.energy ?? 0)
            bucket.materials += Number(r.materials ?? 0)
            bucket.total += Number(row.total_wealth ?? 0)
            sums.set(tier, bucket)
        }

        return Array.from(sums.values()).sort((a, b) => a.tier - b.tier)
    }, [agents, distribution])

    const tierPieData = useMemo(() => distributionByTier.map(t => ({
        name: `Tier ${t.tier}`,
        value: t.total,
        color: t.tier === 1 ? COLORS.tier1 : t.tier === 2 ? COLORS.tier2 : t.tier === 3 ? COLORS.tier3 : COLORS.tier4,
    })), [distributionByTier])

    const criticalAgents = useMemo(() => {
        const dist = distribution?.distribution
        if (!Array.isArray(dist)) return []
        return dist
            .map((row) => {
                const resources = row?.resources || {}
                return {
                    ...row,
                    food: Number(resources.food || 0),
                    energy: Number(resources.energy || 0),
                }
            })
            .filter((row) => row.status !== 'dead' && (row.food < 2 || row.energy < 2))
            .sort((a, b) => {
                const focusFood = focus === 'critical-food'
                const left = focusFood ? Number(a.food) : Number(a.energy)
                const right = focusFood ? Number(b.food) : Number(b.energy)
                return left - right
            })
            .slice(0, 24)
    }, [distribution, focus])

    const aidItems = Array.isArray(aidLifecycle?.items) ? aidLifecycle.items : []

    function statusLabel(status) {
        return String(status || '').replace(/_/g, ' ')
    }

    if (loading) {
        return <div className="loading"><div className="loading-spinner"></div>Loading...</div>
    }

    if (error) {
        return <div className="empty-state">Failed to load resources.</div>
    }

    return (
        <div className="resources-page">
            <div className="page-header">
                <h1>
                    <Package size={32} />
                    Resources
                </h1>
                <p className="page-description">
                    Global resource tracking and distribution
                </p>
            </div>

            {/* Resource Stats */}
            <div className="stats-grid">
                {['food', 'energy', 'materials'].map((resourceType) => {
                    const total = totals?.[resourceType] ?? 0
                    const net = dailyNet?.[resourceType] ?? 0
                    const isPositive = net >= 0
                    const color =
                        resourceType === 'food'
                            ? 'var(--accent-green)'
                            : resourceType === 'energy'
                                ? 'var(--accent-blue)'
                                : 'var(--accent-purple)'

                    return (
                        <div key={resourceType} className="stat-card">
                            <div className="stat-header">
                                <span className="stat-label">{resourceType === 'food' ? 'Total Food' : resourceType === 'energy' ? 'Total Energy' : 'Total Materials'}</span>
                                <div className={`stat-icon ${resourceType === 'food' ? 'green' : resourceType === 'energy' ? 'blue' : 'purple'}`}>
                                    <Package size={18} />
                                </div>
                            </div>
                            <div className="stat-value" style={{ color }}>{formatNumber(total)}</div>
                            <div className={`stat-change ${isPositive ? 'positive' : 'negative'}`}>
                                {isPositive ? <TrendingUp size={14} /> : <TrendingDown size={14} />}
                                <span>{isPositive ? '+' : ''}{formatNumber(net)} net today</span>
                            </div>
                        </div>
                    )
                })}
            </div>

            {secondaryLoading ? (
                <div className="content-grid">
                    <div className="card">
                        <div className="card-header">
                            <h3>Net Resource Change</h3>
                        </div>
                        <div className="card-body">
                            <div className="empty-state">Loading resource history…</div>
                        </div>
                    </div>
                    <div className="card">
                        <div className="card-header">
                            <h3>Wealth by Tier</h3>
                        </div>
                        <div className="card-body">
                            <div className="empty-state">Loading wealth distribution…</div>
                        </div>
                    </div>
                </div>
            ) : (
                <Suspense
                    fallback={
                        <div className="content-grid">
                            <div className="card">
                                <div className="card-body">
                                    <div className="empty-state">Loading charts…</div>
                                </div>
                            </div>
                            <div className="card">
                                <div className="card-body">
                                    <div className="empty-state">Loading charts…</div>
                                </div>
                            </div>
                        </div>
                    }
                >
                    <ResourcesCharts historyChartData={historyChartData} tierPieData={tierPieData} />
                </Suspense>
            )}

            <div className="content-grid" style={{ marginTop: 'var(--spacing-lg)' }}>
                <div className="card">
                    <div className="card-header">
                        <h3>Critical Agent Evidence</h3>
                        <span className="strip-meta">{criticalAgents.length} shown</span>
                    </div>
                    <div className="card-body">
                        {secondaryLoading ? (
                            <div className="empty-state">Loading affected agents…</div>
                        ) : criticalAgents.length === 0 ? (
                            <div className="empty-state compact">No living agents are below critical food or energy thresholds.</div>
                        ) : (
                            <table>
                                <thead>
                                    <tr>
                                        <th>Agent</th>
                                        <th>Status</th>
                                        <th>Food</th>
                                        <th>Energy</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {criticalAgents.map((agent) => (
                                        <tr key={agent.agent_number}>
                                            <td>
                                                <Link to={`/agents/${agent.agent_number}`}>
                                                    {formatAgentDisplayLabel(agent)}
                                                </Link>
                                            </td>
                                            <td>{agent.status}</td>
                                            <td style={{ color: agent.food < 2 ? 'var(--accent-red)' : 'var(--text-secondary)' }}>{formatNumber(agent.food)}</td>
                                            <td style={{ color: agent.energy < 2 ? 'var(--accent-red)' : 'var(--text-secondary)' }}>{formatNumber(agent.energy)}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        )}
                    </div>
                </div>

                <div className="card">
                    <div className="card-header">
                        <h3>Aid Request Lifecycle</h3>
                        <span className="strip-meta">{aidLifecycle?.total || 0} requests</span>
                    </div>
                    <div className="card-body">
                        {secondaryLoading ? (
                            <div className="empty-state">Loading aid requests…</div>
                        ) : aidItems.length === 0 ? (
                            <div className="empty-state compact">No direct aid requests in the current run window.</div>
                        ) : (
                            <div className="aid-lifecycle-list">
                                {aidItems.slice(0, 12).map((item) => (
                                    <div key={item.request_event_id} className={`aid-lifecycle-row status-${item.status}`}>
                                        <div>
                                            <strong>
                                                {item.requester ? formatAgentDisplayLabel(item.requester) : 'Unknown'}
                                            </strong>
                                            {' -> '}
                                            <strong>
                                                {item.target ? formatAgentDisplayLabel(item.target) : 'Unknown'}
                                            </strong>
                                        </div>
                                        <div className="aid-lifecycle-meta">
                                            <span>{formatNumber(item.amount)} {item.resource_type}</span>
                                            <span>{statusLabel(item.status)}</span>
                                            {item.response_event_id && (
                                                <Link to={`/timeline?event=${item.response_event_id}`}>evidence</Link>
                                            )}
                                        </div>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                </div>
            </div>

            {/* Detailed Distribution Table */}
            <div className="card" style={{ marginTop: 'var(--spacing-lg)' }}>
                <div className="card-header">
                    <h3>Distribution by Tier</h3>
                </div>
                <div className="card-body">
                    {secondaryLoading ? (
                        <div className="empty-state">Loading distribution table…</div>
                    ) : distributionByTier.length === 0 ? (
                        <div className="empty-state">No distribution data yet.</div>
                    ) : (
                        <table>
                            <thead>
                                <tr>
                                    <th>Tier</th>
                                    <th>Food</th>
                                    <th>Energy</th>
                                    <th>Materials</th>
                                    <th>Total</th>
                                </tr>
                            </thead>
                            <tbody>
                                {distributionByTier.map(row => (
                                    <tr key={row.tier}>
                                        <td>
                                            <span className={`badge badge-tier-${row.tier}`}>Tier {row.tier}</span>
                                        </td>
                                        <td style={{ color: 'var(--accent-green)' }}>{formatNumber(row.food)}</td>
                                        <td style={{ color: 'var(--accent-blue)' }}>{formatNumber(row.energy)}</td>
                                        <td style={{ color: 'var(--accent-purple)' }}>{formatNumber(row.materials)}</td>
                                        <td><strong>{formatNumber(row.total)}</strong></td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    )}
                </div>
            </div>

            <style>{`
        .chart-legend {
          display: flex;
          justify-content: center;
          gap: var(--spacing-lg);
          margin-top: var(--spacing-md);
          font-size: 0.8125rem;
          color: var(--text-secondary);
          flex-wrap: wrap;
        }

        .legend-dot {
          display: inline-block;
          width: 10px;
          height: 10px;
          border-radius: 50%;
          margin-right: var(--spacing-xs);
        }

        .aid-lifecycle-list {
          display: flex;
          flex-direction: column;
          gap: var(--spacing-sm);
        }

        .aid-lifecycle-row {
          border: 1px solid var(--border-color);
          border-radius: var(--radius-md);
          padding: var(--spacing-sm) var(--spacing-md);
          background: rgba(255, 255, 255, 0.02);
        }

        .aid-lifecycle-meta {
          display: flex;
          flex-wrap: wrap;
          gap: var(--spacing-sm);
          color: var(--text-muted);
          font-size: 0.82rem;
          text-transform: capitalize;
          margin-top: 4px;
        }

        .aid-lifecycle-row.status-fulfilled_by_trade {
          border-left: 3px solid var(--accent-green);
        }

        .aid-lifecycle-row.status-refused,
        .aid-lifecycle-row.status-mechanically_unaffordable {
          border-left: 3px solid var(--accent-red);
        }

        .aid-lifecycle-row.status-reserve_covered {
          border-left: 3px solid var(--accent-blue);
        }
      `}</style>
        </div>
    )
}
