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

// Mock data for demo
const mockStats = {
    activeAgents: 87,
    dormantAgents: 13,
    activeProposals: 5,
    passedLaws: 3,
    totalFood: 2847,
    maxFood: 5000,
    totalEnergy: 1923,
    maxEnergy: 4000,
    totalMaterials: 734,
    maxMaterials: 2000,
    criticalFoodAgents: 3,
    criticalEnergyAgents: 1,
    totalMessages: 12847,
    dayNumber: 5,
    lastActivity: new Date(Date.now() - 12000).toISOString(),
}

const mockRecentProposals = [
    { id: 1, title: 'Establish Daily Work Hours', author: 'Agent #5', votes_for: 34, votes_against: 12, status: 'active' },
    { id: 2, title: 'Create Resource Committee', author: 'Agent #42', votes_for: 45, votes_against: 8, status: 'active' },
    { id: 3, title: 'Minimum Food Reserve Law', author: 'Agent #17', votes_for: 67, votes_against: 23, status: 'passed' },
]

const mockTopAgents = [
    { id: 1, agent_number: 42, display_name: 'Coordinator', tier: 1, status: 'active', food: 45, actions: 156, personality_type: 'efficiency' },
    { id: 2, agent_number: 17, display_name: null, tier: 1, status: 'active', food: 38, actions: 142, personality_type: 'equality' },
    { id: 3, agent_number: 5, display_name: 'Builder', tier: 2, status: 'active', food: 35, actions: 128, personality_type: 'stability' },
    { id: 4, agent_number: 88, display_name: null, tier: 3, status: 'active', food: 32, actions: 119, personality_type: 'freedom' },
    { id: 5, agent_number: 23, display_name: 'Trader', tier: 2, status: 'active', food: 31, actions: 112, personality_type: 'neutral' },
]

export default function Dashboard() {
    const [stats, setStats] = useState(null)
    const [proposals, setProposals] = useState([])
    const [topAgents, setTopAgents] = useState([])
    const [loading, setLoading] = useState(true)
    const [isLive, setIsLive] = useState(true)

    useEffect(() => {
        const fetchData = async () => {
            try {
                // Simulate API delay for skeleton demo
                await new Promise(resolve => setTimeout(resolve, 800))

                // Try to fetch real data
                // const health = await api.getHealth()
                // const agents = await api.getAgents()

                setStats(mockStats)
                setProposals(mockRecentProposals)
                setTopAgents(mockTopAgents)
            } catch (error) {
                console.log('Using demo data')
                setStats(mockStats)
                setProposals(mockRecentProposals)
                setTopAgents(mockTopAgents)
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
                                            <td>{proposal.author}</td>
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
                                        <th>Food</th>
                                        <th>Actions</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {topAgents.map(agent => (
                                        <tr key={agent.id}>
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
                                            <td>{agent.food}</td>
                                            <td>{agent.actions}</td>
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
