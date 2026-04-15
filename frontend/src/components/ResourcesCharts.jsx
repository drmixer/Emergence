const CHART_HEIGHT = 300
const CHART_WIDTH = 640
const CHART_PADDING = { top: 16, right: 18, bottom: 34, left: 42 }
const GRID_TICKS = 4

function formatNumber(n) {
    if (n === null || n === undefined || Number.isNaN(Number(n))) return '—'
    return Number(n).toLocaleString(undefined, { maximumFractionDigits: 2 })
}

function polarToCartesian(cx, cy, radius, angleInDegrees) {
    const angleInRadians = ((angleInDegrees - 90) * Math.PI) / 180
    return {
        x: cx + radius * Math.cos(angleInRadians),
        y: cy + radius * Math.sin(angleInRadians),
    }
}

function describeArc(cx, cy, radius, startAngle, endAngle) {
    const start = polarToCartesian(cx, cy, radius, endAngle)
    const end = polarToCartesian(cx, cy, radius, startAngle)
    const largeArcFlag = endAngle - startAngle <= 180 ? '0' : '1'
    return [
        'M', start.x, start.y,
        'A', radius, radius, 0, largeArcFlag, 0, end.x, end.y,
    ].join(' ')
}

function buildSeriesGeometry(data, key) {
    const chartInnerWidth = CHART_WIDTH - CHART_PADDING.left - CHART_PADDING.right
    const chartInnerHeight = CHART_HEIGHT - CHART_PADDING.top - CHART_PADDING.bottom
    const values = data.map((row) => Number(row?.[key] || 0))
    const minValue = Math.min(0, ...values)
    const maxValue = Math.max(0, ...values)
    const valueSpan = maxValue - minValue || 1
    const zeroY = CHART_PADDING.top + ((maxValue - 0) / valueSpan) * chartInnerHeight

    const points = data.map((row, index) => {
        const x = CHART_PADDING.left + (chartInnerWidth * index) / Math.max(1, data.length - 1)
        const value = Number(row?.[key] || 0)
        const y = CHART_PADDING.top + ((maxValue - value) / valueSpan) * chartInnerHeight
        return { x, y, value, day: String(row?.day || '') }
    })

    const linePath = points.map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x} ${point.y}`).join(' ')
    const areaPath = points.length === 0
        ? ''
        : `${linePath} L ${points[points.length - 1].x} ${zeroY} L ${points[0].x} ${zeroY} Z`

    return {
        points,
        linePath,
        areaPath,
        minValue,
        maxValue,
        zeroY,
    }
}

function LineAreaChart({ data }) {
    const food = buildSeriesGeometry(data, 'food')
    const energy = buildSeriesGeometry(data, 'energy')
    const materials = buildSeriesGeometry(data, 'materials')
    const chartMin = Math.min(food.minValue, energy.minValue, materials.minValue)
    const chartMax = Math.max(food.maxValue, energy.maxValue, materials.maxValue)
    const yTicks = Array.from({ length: GRID_TICKS + 1 }, (_, index) => {
        const ratio = index / GRID_TICKS
        const value = chartMax - (chartMax - chartMin) * ratio
        const y = CHART_PADDING.top + ((value - chartMax) / (chartMin - chartMax || -1)) * (CHART_HEIGHT - CHART_PADDING.top - CHART_PADDING.bottom)
        return { value, y }
    })
    const labelIndexes = [0, Math.floor((data.length - 1) / 2), data.length - 1]
        .filter((value, index, array) => value >= 0 && array.indexOf(value) === index)

    return (
        <svg viewBox={`0 0 ${CHART_WIDTH} ${CHART_HEIGHT}`} className="resource-chart-svg" role="img" aria-label="Net resource change over time">
            <rect x="0" y="0" width={CHART_WIDTH} height={CHART_HEIGHT} fill="transparent" />

            {yTicks.map((tick) => (
                <g key={`grid-${tick.y}`}>
                    <line
                        x1={CHART_PADDING.left}
                        y1={tick.y}
                        x2={CHART_WIDTH - CHART_PADDING.right}
                        y2={tick.y}
                        stroke="rgba(255,255,255,0.08)"
                        strokeDasharray="4 6"
                    />
                    <text
                        x={CHART_PADDING.left - 10}
                        y={tick.y + 4}
                        textAnchor="end"
                        fill="rgba(255,255,255,0.55)"
                        fontSize="11"
                    >
                        {formatNumber(tick.value)}
                    </text>
                </g>
            ))}

            <line
                x1={CHART_PADDING.left}
                y1={food.zeroY}
                x2={CHART_WIDTH - CHART_PADDING.right}
                y2={food.zeroY}
                stroke="rgba(255,255,255,0.18)"
            />

            <path d={food.areaPath} fill="rgba(16, 185, 129, 0.16)" />
            <path d={energy.areaPath} fill="rgba(59, 130, 246, 0.14)" />
            <path d={materials.areaPath} fill="rgba(139, 92, 246, 0.14)" />

            <path d={food.linePath} fill="none" stroke="#10b981" strokeWidth="2.5" />
            <path d={energy.linePath} fill="none" stroke="#3b82f6" strokeWidth="2.5" />
            <path d={materials.linePath} fill="none" stroke="#8b5cf6" strokeWidth="2.5" />

            {labelIndexes.map((index) => {
                const point = food.points[index]
                if (!point) return null
                return (
                    <text
                        key={`label-${index}`}
                        x={point.x}
                        y={CHART_HEIGHT - 8}
                        textAnchor="middle"
                        fill="rgba(255,255,255,0.55)"
                        fontSize="11"
                    >
                        {point.day}
                    </text>
                )
            })}
        </svg>
    )
}

function DonutChart({ data }) {
    const total = data.reduce((sum, item) => sum + Number(item?.value || 0), 0)
    let currentAngle = 0

    return (
        <svg viewBox="0 0 240 240" className="resource-donut-svg" role="img" aria-label="Wealth share by tier">
            <circle cx="120" cy="120" r="70" fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth="28" />
            {data.map((item) => {
                const value = Number(item?.value || 0)
                const angle = total > 0 ? (value / total) * 360 : 0
                const startAngle = currentAngle
                const endAngle = currentAngle + angle
                currentAngle = endAngle
                return (
                    <path
                        key={item.name}
                        d={describeArc(120, 120, 70, startAngle, endAngle)}
                        fill="none"
                        stroke={item.color}
                        strokeWidth="28"
                        strokeLinecap="butt"
                    />
                )
            })}
            <text x="120" y="112" textAnchor="middle" fill="rgba(255,255,255,0.65)" fontSize="12">
                Total Wealth
            </text>
            <text x="120" y="136" textAnchor="middle" fill="white" fontSize="20" fontWeight="700">
                {formatNumber(total)}
            </text>
        </svg>
    )
}

export default function ResourcesCharts({ historyChartData, tierPieData }) {
    return (
        <div className="content-grid">
            <div className="card">
                <div className="card-header">
                    <h3>Net Resource Change</h3>
                </div>
                <div className="card-body">
                    {historyChartData.length === 0 ? (
                        <div className="empty-state">No resource history yet.</div>
                    ) : (
                        <>
                            <div className="resource-chart-wrap">
                                <LineAreaChart data={historyChartData} />
                            </div>
                            <div className="chart-legend">
                                <span><span className="legend-dot" style={{ background: '#10b981' }}></span> Food</span>
                                <span><span className="legend-dot" style={{ background: '#3b82f6' }}></span> Energy</span>
                                <span><span className="legend-dot" style={{ background: '#8b5cf6' }}></span> Materials</span>
                            </div>
                        </>
                    )}
                </div>
            </div>

            <div className="card">
                <div className="card-header">
                    <h3>Wealth by Tier</h3>
                </div>
                <div className="card-body">
                    {tierPieData.length === 0 ? (
                        <div className="empty-state">No distribution data yet.</div>
                    ) : (
                        <>
                            <div className="resource-chart-wrap resource-donut-wrap">
                                <DonutChart data={tierPieData} />
                            </div>
                            <div className="chart-legend">
                                {tierPieData.map((item) => (
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

            <style>{`
                .resource-chart-wrap {
                    width: 100%;
                    min-height: 300px;
                }

                .resource-chart-svg,
                .resource-donut-svg {
                    width: 100%;
                    height: auto;
                    display: block;
                }

                .resource-donut-wrap {
                    max-width: 360px;
                    margin: 0 auto;
                }
            `}</style>
        </div>
    )
}
