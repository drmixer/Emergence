import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import {
    Users,
    FileText,
    Scale,
    Package,
    TrendingUp,
    TrendingDown,
    Activity,
    AlertTriangle,
    Zap,
    Apple,
    Battery,
    Box
} from 'lucide-react'
import { api } from '../services/api'
import ActivityPulse from '../components/ActivityPulse'
import { ResourceBar, CriticalAgentsBanner } from '../components/ResourceBar'
import { SkeletonStatCard, SkeletonTable } from '../components/Skeleton'

function sumWorldResource(resources, key) {
    const totals = resources?.totals || {}
    const pool = resources?.common_pool || {}
    const a = Number(totals[key] || 0)
    const b = Number(pool[key] || 0)
    return a + b
}

export default function Dashboard() {
    const [stats, setStats] = useState(null)
    const [proposals, setProposals] = useState([])
    const [topAgents, setTopAgents] = useState([])
    const [loading, setLoading] = useState(true)
    const [isLive, setIsLive] = useState(true)
    const [error, setError] = useState(null)

    useEffect(() => {
        const fetchData = async () => {
            try {
                setError(null)
                const [overview, resources, activeProposals, activityLeaderboard] = await Promise.all([
                    api.getAnalyticsOverview(),
                    api.getResources(),
                    api.fetch('/api/proposals?status=active&limit=5'),
                    api.fetch('/api/analytics/leaderboards/activity?limit=5&hours=24'),
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
            } catch (e) {
                setError('Failed to load live data.')
                setStats(null)
                setProposals([])
                setTopAgents([])
            } finally {
                setLoading(false)
            }
        }

        fetchData()
    }, [])

    // Check for pre-launch state
    const isPreLaunch = stats && stats.dayNumber === 0 && stats.totalMessages === 0

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
                                                {proposal.author?.display_name ||
                                                    (proposal.author?.agent_number
                                                        ? `Agent #${proposal.author.agent_number}`
                                                        : 'Unknown')}
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
                                                    {agent.display_name || `Agent #${agent.agent_number}`}
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

            <style>{`
                .resource-grid {
                    display: grid;
                    grid-template-columns: repeat(3, 1fr);
                    gap: var(--spacing-lg);
                    margin-bottom: var(--spacing-xl);
                }
                
                @media (max-width: 768px) {
                    .resource-grid {
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
