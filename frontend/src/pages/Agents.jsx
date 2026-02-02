import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { Users, Search, Filter } from 'lucide-react'
import { api } from '../services/api'
import AgentAvatar, { PersonalityBadge } from '../components/AgentAvatar'

// Models for display
const modelNames = {
    'claude-sonnet-4': 'Claude Sonnet 4',
    'gpt-4o-mini': 'GPT-4o Mini',
    'claude-haiku': 'Claude Haiku',
    'llama-3.3-70b': 'Llama 3.3 70B',
    'llama-3.1-8b': 'Llama 3.1 8B',
    'gemini-flash': 'Gemini Flash',
}

// Mock agents for demo
const generateMockAgents = () => {
    const agents = []
    const tiers = [
        { tier: 1, count: 10, models: ['claude-sonnet-4'] },
        { tier: 2, count: 20, models: ['gpt-4o-mini', 'claude-haiku'] },
        { tier: 3, count: 40, models: ['llama-3.3-70b'] },
        { tier: 4, count: 30, models: ['llama-3.1-8b', 'gemini-flash'] },
    ]
    const personalities = ['efficiency', 'equality', 'freedom', 'stability', 'neutral']

    let id = 1
    for (const { tier, count, models } of tiers) {
        for (let i = 0; i < count; i++) {
            agents.push({
                id,
                agent_number: id,
                display_name: Math.random() > 0.7 ? `Agent${id}Name` : null,
                model_type: models[Math.floor(Math.random() * models.length)],
                tier,
                personality_type: personalities[Math.floor(Math.random() * personalities.length)],
                status: Math.random() > 0.13 ? 'active' : 'dormant',
                food: Math.floor(Math.random() * 30) + 5,
                energy: Math.floor(Math.random() * 25) + 3,
                materials: Math.floor(Math.random() * 15),
            })
            id++
        }
    }
    return agents
}

export default function Agents() {
    const [agents, setAgents] = useState(generateMockAgents())
    const [loading, setLoading] = useState(false)
    const [filters, setFilters] = useState({
        status: '',
        tier: '',
        personality: '',
        search: '',
    })

    useEffect(() => {
        const fetchAgents = async () => {
            try {
                // const data = await api.getAgents()
                // setAgents(data)
            } catch (error) {
                console.log('Using demo data')
            }
        }
        fetchAgents()
    }, [])

    const filteredAgents = agents.filter(agent => {
        if (filters.status && agent.status !== filters.status) return false
        if (filters.tier && agent.tier !== parseInt(filters.tier)) return false
        if (filters.personality && agent.personality_type !== filters.personality) return false
        if (filters.search) {
            const searchLower = filters.search.toLowerCase()
            const name = agent.display_name || `Agent #${agent.agent_number}`
            if (!name.toLowerCase().includes(searchLower) &&
                !agent.agent_number.toString().includes(searchLower)) {
                return false
            }
        }
        return true
    })

    return (
        <div className="agents-page">
            <div className="page-header">
                <h1>
                    <Users size={32} />
                    Agents
                </h1>
                <p className="page-description">
                    All 100 AI agents in the simulation
                </p>
            </div>

            {/* Filters */}
            <div className="filters">
                <div className="filter-group">
                    <label className="filter-label">Search</label>
                    <div style={{ position: 'relative' }}>
                        <Search size={16} style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }} />
                        <input
                            type="text"
                            placeholder="Search agents..."
                            value={filters.search}
                            onChange={(e) => setFilters({ ...filters, search: e.target.value })}
                            style={{ paddingLeft: 36, width: 200 }}
                        />
                    </div>
                </div>

                <div className="filter-group">
                    <label className="filter-label">Status</label>
                    <select
                        value={filters.status}
                        onChange={(e) => setFilters({ ...filters, status: e.target.value })}
                    >
                        <option value="">All</option>
                        <option value="active">Active</option>
                        <option value="dormant">Dormant</option>
                    </select>
                </div>

                <div className="filter-group">
                    <label className="filter-label">Tier</label>
                    <select
                        value={filters.tier}
                        onChange={(e) => setFilters({ ...filters, tier: e.target.value })}
                    >
                        <option value="">All</option>
                        <option value="1">Tier 1 (Claude Sonnet)</option>
                        <option value="2">Tier 2 (GPT-4o/Haiku)</option>
                        <option value="3">Tier 3 (Llama 70B)</option>
                        <option value="4">Tier 4 (Llama 8B/Flash)</option>
                    </select>
                </div>

                <div className="filter-group">
                    <label className="filter-label">Personality</label>
                    <select
                        value={filters.personality}
                        onChange={(e) => setFilters({ ...filters, personality: e.target.value })}
                    >
                        <option value="">All</option>
                        <option value="efficiency">Efficiency</option>
                        <option value="equality">Equality</option>
                        <option value="freedom">Freedom</option>
                        <option value="stability">Stability</option>
                        <option value="neutral">Neutral</option>
                    </select>
                </div>
            </div>

            <div style={{ marginBottom: 'var(--spacing-md)', color: 'var(--text-secondary)', fontSize: '0.875rem' }}>
                Showing {filteredAgents.length} of {agents.length} agents
            </div>

            {/* Agent Grid */}
            <div className="agent-grid">
                {filteredAgents.map(agent => (
                    <Link to={`/agents/${agent.agent_number}`} key={agent.id} style={{ textDecoration: 'none' }}>
                        <div className="agent-card">
                            <div className="agent-header">
                                <AgentAvatar
                                    agentNumber={agent.agent_number}
                                    tier={agent.tier}
                                    personality={agent.personality_type}
                                    status={agent.status}
                                    size="medium"
                                />
                                <div className="agent-info">
                                    <h4>{agent.display_name || `Agent #${agent.agent_number}`}</h4>
                                    <span className="agent-model">{modelNames[agent.model_type]}</span>
                                </div>
                                <span className={`badge badge-${agent.status}`}>
                                    {agent.status}
                                </span>
                            </div>

                            <div className="agent-meta">
                                <span className={`badge badge-tier-${agent.tier}`}>Tier {agent.tier}</span>
                                <PersonalityBadge personality={agent.personality_type} showIcon={false} />
                            </div>

                            <div className="agent-stats">
                                <div className="agent-stat">
                                    <div className="agent-stat-value" style={{ color: 'var(--accent-green)' }}>{agent.food}</div>
                                    <div className="agent-stat-label">Food</div>
                                </div>
                                <div className="agent-stat">
                                    <div className="agent-stat-value" style={{ color: 'var(--accent-blue)' }}>{agent.energy}</div>
                                    <div className="agent-stat-label">Energy</div>
                                </div>
                                <div className="agent-stat">
                                    <div className="agent-stat-value" style={{ color: 'var(--accent-purple)' }}>{agent.materials}</div>
                                    <div className="agent-stat-label">Materials</div>
                                </div>
                            </div>
                        </div>
                    </Link>
                ))}
            </div>

            <style>{`
        .agent-meta {
          display: flex;
          align-items: center;
          gap: var(--spacing-sm);
          margin-bottom: var(--spacing-md);
        }
        
        .personality-badge {
          font-size: 0.75rem;
          color: var(--text-muted);
          text-transform: capitalize;
        }
      `}</style>
        </div>
    )
}
