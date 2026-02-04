import { useEffect, useMemo, useState } from 'react'
import { Package, TrendingUp, TrendingDown } from 'lucide-react'
import {
    ResponsiveContainer,
    AreaChart,
    Area,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    PieChart,
    Pie,
    Cell,
} from 'recharts'
import { api } from '../services/api'

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
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState(null)
    const [resources, setResources] = useState(null)
    const [history, setHistory] = useState(null)
    const [distribution, setDistribution] = useState(null)
    const [agents, setAgents] = useState([])

    useEffect(() => {
        async function load() {
            setLoading(true)
            setError(null)
            try {
                const [res, hist, dist, agentList] = await Promise.all([
                    api.getResources(),
                    api.getResourceHistory(),
                    api.getResourceDistribution(),
                    api.getAgents(),
                ])
                setResources(res)
                setHistory(hist)
                setDistribution(dist)
                setAgents(Array.isArray(agentList) ? agentList : [])
            } catch (e) {
                setError(e)
            } finally {
                setLoading(false)
            }
        }
        load()
    }, [])

    const totals = resources?.totals || {}

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

            {/* Charts */}
            <div className="content-grid">
                {/* Net Production Chart */}
                <div className="card">
                    <div className="card-header">
                        <h3>Net Resource Change</h3>
                    </div>
                    <div className="card-body">
                        <div style={{ width: '100%', height: 300 }}>
                            <ResponsiveContainer>
                                <AreaChart data={historyChartData}>
                                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" opacity={0.2} />
                                    <XAxis dataKey="day" stroke="var(--text-muted)" tick={{ fontSize: 12 }} />
                                    <YAxis stroke="var(--text-muted)" tick={{ fontSize: 12 }} />
                                    <Tooltip
                                        contentStyle={{
                                            background: 'var(--bg-card)',
                                            border: '1px solid var(--border-color)',
                                            borderRadius: 'var(--radius-md)',
                                        }}
                                    />
                                    <Area type="monotone" dataKey="food" stackId="1" stroke="#10b981" fill="rgba(16, 185, 129, 0.25)" />
                                    <Area type="monotone" dataKey="energy" stackId="1" stroke="#3b82f6" fill="rgba(59, 130, 246, 0.25)" />
                                    <Area type="monotone" dataKey="materials" stackId="1" stroke="#8b5cf6" fill="rgba(139, 92, 246, 0.25)" />
                                </AreaChart>
                            </ResponsiveContainer>
                        </div>
                        <div className="chart-legend">
                            <span><span className="legend-dot" style={{ background: '#10b981' }}></span> Food</span>
                            <span><span className="legend-dot" style={{ background: '#3b82f6' }}></span> Energy</span>
                            <span><span className="legend-dot" style={{ background: '#8b5cf6' }}></span> Materials</span>
                        </div>
                    </div>
                </div>

                {/* Distribution by Tier */}
                <div className="card">
                    <div className="card-header">
                        <h3>Wealth by Tier</h3>
                    </div>
                    <div className="card-body">
                        {tierPieData.length === 0 ? (
                            <div className="empty-state">No distribution data yet.</div>
                        ) : (
                            <>
                                <div style={{ width: '100%', height: 300 }}>
                                    <ResponsiveContainer>
                                        <PieChart>
                                            <Pie
                                                data={tierPieData}
                                                innerRadius={60}
                                                outerRadius={100}
                                                paddingAngle={5}
                                                dataKey="value"
                                            >
                                                {tierPieData.map((entry, index) => (
                                                    <Cell key={`cell-${index}`} fill={entry.color} />
                                                ))}
                                            </Pie>
                                            <Tooltip
                                                formatter={(value) => formatNumber(value)}
                                                contentStyle={{
                                                    background: 'var(--bg-card)',
                                                    border: '1px solid var(--border-color)',
                                                    borderRadius: 'var(--radius-md)',
                                                }}
                                            />
                                        </PieChart>
                                    </ResponsiveContainer>
                                </div>
                                <div className="chart-legend">
                                    {tierPieData.map(item => (
                                        <span key={item.name}>
                                            <span className="legend-dot" style={{ background: item.color }}></span>
                                            {item.name}
                                        </span>
                                    ))}
                                </div>
                            </>
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
                    {distributionByTier.length === 0 ? (
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
      `}</style>
        </div>
    )
}

