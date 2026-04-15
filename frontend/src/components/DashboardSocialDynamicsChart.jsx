const WIDTH = 640
const HEIGHT = 240
const PADDING = { top: 16, right: 16, bottom: 28, left: 34 }

function formatNumber(value) {
    return Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: 0 })
}

function buildLine(data, key) {
    const innerWidth = WIDTH - PADDING.left - PADDING.right
    const innerHeight = HEIGHT - PADDING.top - PADDING.bottom
    const values = data.map((row) => Number(row?.[key] || 0))
    const maxValue = Math.max(1, ...values)

    const points = data.map((row, index) => {
        const x = PADDING.left + (innerWidth * index) / Math.max(1, data.length - 1)
        const value = Number(row?.[key] || 0)
        const y = PADDING.top + innerHeight - (value / maxValue) * innerHeight
        return { x, y, value }
    })

    return {
        maxValue,
        points,
        path: points.map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x} ${point.y}`).join(' '),
    }
}

export default function DashboardSocialDynamicsChart({ data }) {
    const conflict = buildLine(data, 'conflict')
    const cooperation = buildLine(data, 'cooperation')
    const alliances = buildLine(data, 'alliances')
    const maxValue = Math.max(conflict.maxValue, cooperation.maxValue, alliances.maxValue)
    const innerHeight = HEIGHT - PADDING.top - PADDING.bottom
    const yTicks = [0, 0.33, 0.66, 1].map((ratio) => {
        const value = Math.round(maxValue * (1 - ratio))
        const y = PADDING.top + innerHeight * ratio
        return { value, y }
    })
    const xLabels = [0, Math.floor((data.length - 1) / 2), data.length - 1]
        .filter((index, position, array) => index >= 0 && array.indexOf(index) === position)

    return (
        <div className="dashboard-social-chart">
            <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className="dashboard-social-chart-svg" role="img" aria-label="Social dynamics for the last 7 days">
                {yTicks.map((tick) => (
                    <g key={`tick-${tick.y}`}>
                        <line
                            x1={PADDING.left}
                            y1={tick.y}
                            x2={WIDTH - PADDING.right}
                            y2={tick.y}
                            stroke="rgba(255,255,255,0.08)"
                            strokeDasharray="4 6"
                        />
                        <text
                            x={PADDING.left - 8}
                            y={tick.y + 4}
                            textAnchor="end"
                            fill="rgba(255,255,255,0.55)"
                            fontSize="11"
                        >
                            {formatNumber(tick.value)}
                        </text>
                    </g>
                ))}

                <path d={conflict.path} fill="none" stroke="#ef4444" strokeWidth="2.5" />
                <path d={cooperation.path} fill="none" stroke="#22c55e" strokeWidth="2.5" />
                <path d={alliances.path} fill="none" stroke="#60a5fa" strokeWidth="2.5" />

                {xLabels.map((index) => {
                    const point = conflict.points[index]
                    const row = data[index]
                    if (!point || !row) return null
                    return (
                        <text
                            key={`label-${index}`}
                            x={point.x}
                            y={HEIGHT - 6}
                            textAnchor="middle"
                            fill="rgba(255,255,255,0.55)"
                            fontSize="11"
                        >
                            {row.day}
                        </text>
                    )
                })}
            </svg>

            <div className="dashboard-social-chart-legend">
                <span><span className="legend-dot" style={{ background: '#ef4444' }}></span> Conflict</span>
                <span><span className="legend-dot" style={{ background: '#22c55e' }}></span> Cooperation</span>
                <span><span className="legend-dot" style={{ background: '#60a5fa' }}></span> Alliances</span>
            </div>

            <style>{`
                .dashboard-social-chart-svg {
                    width: 100%;
                    height: auto;
                    display: block;
                }

                .dashboard-social-chart-legend {
                    display: flex;
                    justify-content: center;
                    gap: 1rem;
                    flex-wrap: wrap;
                    margin-top: 0.75rem;
                    color: var(--text-secondary);
                    font-size: 0.82rem;
                }
            `}</style>
        </div>
    )
}
