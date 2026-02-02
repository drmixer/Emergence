import { useState } from 'react'
import { Package, TrendingUp, TrendingDown } from 'lucide-react'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, AreaChart, Area, PieChart, Pie, Cell } from 'recharts'

// Mock resource history data
const resourceHistory = [
    { day: 1, food: 1000, energy: 1000, materials: 500 },
    { day: 2, food: 1050, energy: 980, materials: 520 },
    { day: 3, food: 1120, energy: 1020, materials: 535 },
    { day: 4, food: 1180, energy: 1050, materials: 550 },
    { day: 5, food: 1250, energy: 1080, materials: 580 },
    { day: 6, food: 1320, energy: 1100, materials: 600 },
    { day: 7, food: 1400, energy: 1150, materials: 620 },
    { day: 8, food: 1480, energy: 1200, materials: 650 },
    { day: 9, food: 1550, energy: 1250, materials: 680 },
    { day: 10, food: 1620, energy: 1300, materials: 700 },
    { day: 11, food: 1700, energy: 1350, materials: 720 },
    { day: 12, food: 1780, energy: 1400, materials: 734 },
]

// Distribution by tier
const distributionByTier = [
    { tier: 'Tier 1', food: 450, energy: 380, materials: 120 },
    { tier: 'Tier 2', food: 820, energy: 640, materials: 210 },
    { tier: 'Tier 3', food: 1100, energy: 920, materials: 280 },
    { tier: 'Tier 4', food: 780, energy: 620, materials: 190 },
]

const COLORS = {
    tier1: '#f59e0b',
    tier2: '#8b5cf6',
    tier3: '#3b82f6',
    tier4: '#6b7280',
}

const tierPieData = [
    { name: 'Tier 1', value: 570, color: COLORS.tier1 },
    { name: 'Tier 2', value: 1670, color: COLORS.tier2 },
    { name: 'Tier 3', value: 2300, color: COLORS.tier3 },
    { name: 'Tier 4', value: 1590, color: COLORS.tier4 },
]

export default function Resources() {
    const [selectedResource, setSelectedResource] = useState('all')

    const currentTotals = {
        food: 2847,
        energy: 1923,
        materials: 734,
    }

    const dailyChanges = {
        food: +87,
        energy: +43,
        materials: +12,
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
                <div className="stat-card">
                    <div className="stat-header">
                        <span className="stat-label">Total Food</span>
                        <div className="stat-icon green">
                            <Package size={18} />
                        </div>
                    </div>
                    <div className="stat-value">{currentTotals.food.toLocaleString()}</div>
                    <div className={`stat-change ${dailyChanges.food >= 0 ? 'positive' : 'negative'}`}>
                        {dailyChanges.food >= 0 ? <TrendingUp size={14} /> : <TrendingDown size={14} />}
                        <span>{dailyChanges.food >= 0 ? '+' : ''}{dailyChanges.food} today</span>
                    </div>
                </div>

                <div className="stat-card">
                    <div className="stat-header">
                        <span className="stat-label">Total Energy</span>
                        <div className="stat-icon blue">
                            <Package size={18} />
                        </div>
                    </div>
                    <div className="stat-value">{currentTotals.energy.toLocaleString()}</div>
                    <div className={`stat-change ${dailyChanges.energy >= 0 ? 'positive' : 'negative'}`}>
                        {dailyChanges.energy >= 0 ? <TrendingUp size={14} /> : <TrendingDown size={14} />}
                        <span>{dailyChanges.energy >= 0 ? '+' : ''}{dailyChanges.energy} today</span>
                    </div>
                </div>

                <div className="stat-card">
                    <div className="stat-header">
                        <span className="stat-label">Total Materials</span>
                        <div className="stat-icon purple">
                            <Package size={18} />
                        </div>
                    </div>
                    <div className="stat-value">{currentTotals.materials.toLocaleString()}</div>
                    <div className={`stat-change ${dailyChanges.materials >= 0 ? 'positive' : 'negative'}`}>
                        {dailyChanges.materials >= 0 ? <TrendingUp size={14} /> : <TrendingDown size={14} />}
                        <span>{dailyChanges.materials >= 0 ? '+' : ''}{dailyChanges.materials} today</span>
                    </div>
                </div>
            </div>

            {/* Charts */}
            <div className="content-grid">
                {/* Resource History Chart */}
                <div className="card">
                    <div className="card-header">
                        <h3>Resource History</h3>
                    </div>
                    <div className="card-body">
                        <div style={{ width: '100%', height: 300 }}>
                            <ResponsiveContainer>
                                <AreaChart data={resourceHistory}>
                                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" />
                                    <XAxis dataKey="day" stroke="var(--text-muted)" tick={{ fill: 'var(--text-muted)' }} />
                                    <YAxis stroke="var(--text-muted)" tick={{ fill: 'var(--text-muted)' }} />
                                    <Tooltip
                                        contentStyle={{
                                            background: 'var(--bg-card)',
                                            border: '1px solid var(--border-color)',
                                            borderRadius: 'var(--radius-md)',
                                        }}
                                        labelStyle={{ color: 'var(--text-primary)' }}
                                    />
                                    <Area type="monotone" dataKey="food" stackId="1" stroke="#10b981" fill="rgba(16, 185, 129, 0.3)" />
                                    <Area type="monotone" dataKey="energy" stackId="1" stroke="#3b82f6" fill="rgba(59, 130, 246, 0.3)" />
                                    <Area type="monotone" dataKey="materials" stackId="1" stroke="#8b5cf6" fill="rgba(139, 92, 246, 0.3)" />
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
                        <h3>Distribution by Tier</h3>
                    </div>
                    <div className="card-body">
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
                    </div>
                </div>
            </div>

            {/* Detailed Distribution Table */}
            <div className="card" style={{ marginTop: 'var(--spacing-lg)' }}>
                <div className="card-header">
                    <h3>Detailed Distribution</h3>
                </div>
                <div className="card-body">
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
                                        <span className={`badge badge-tier-${row.tier.split(' ')[1]}`}>{row.tier}</span>
                                    </td>
                                    <td style={{ color: 'var(--accent-green)' }}>{row.food}</td>
                                    <td style={{ color: 'var(--accent-blue)' }}>{row.energy}</td>
                                    <td style={{ color: 'var(--accent-purple)' }}>{row.materials}</td>
                                    <td><strong>{row.food + row.energy + row.materials}</strong></td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
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
