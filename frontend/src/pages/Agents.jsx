import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Users, Search, Filter } from 'lucide-react'
import { api } from '../services/api'
import AgentAvatar, { PersonalityBadge } from '../components/AgentAvatar'
import { formatDistanceToNow } from 'date-fns'
import { AGENT_ALIAS_HELP_TEXT, formatAgentDisplayLabel } from '../utils/agentIdentity'

// Models for display
const modelNames = {
    'claude-sonnet-4': 'Claude Sonnet 4',
    'gpt-4o-mini': 'GPT-4o Mini',
    'claude-haiku': 'Claude Haiku',
    'llama-3.3-70b': 'Llama 3.3 70B',
    'llama-3.1-8b': 'Llama 3.1 8B',
    'gemini-flash': 'Gemini Flash',
}

export default function Agents() {
    const [agents, setAgents] = useState([])
    const [loading, setLoading] = useState(true)
    const [filters, setFilters] = useState({
        status: '',
        tier: '',
        personality: '',
        search: '',
    })

    useEffect(() => {
        const fetchAgents = async () => {
            setLoading(true)
            try {
                const data = await api.getAgents({
                    status: filters.status || undefined,
                    tier: filters.tier || undefined,
                    personality_type: filters.personality || undefined,
                })
                setAgents(Array.isArray(data) ? data : [])
            } catch (_error) {
                setAgents([])
            } finally {
                setLoading(false)
            }
        }
        fetchAgents()
    }, [filters.status, filters.tier, filters.personality])

    const filteredAgents = useMemo(() => agents.filter(agent => {
        if (filters.status && agent.status !== filters.status) return false
        if (filters.tier && agent.tier !== parseInt(filters.tier)) return false
        if (filters.personality && agent.personality_type !== filters.personality) return false
        if (filters.search) {
            const searchLower = filters.search.toLowerCase()
            const name = formatAgentDisplayLabel(agent)
            if (!name.toLowerCase().includes(searchLower) &&
                !agent.agent_number.toString().includes(searchLower)) {
                return false
            }
        }
        return true
    }), [agents, filters.personality, filters.search, filters.status, filters.tier])

    return (
        <div className="agents-page">
            <div className="page-header">
                <h1>
                    <Users size={32} />
                    Agents
                </h1>
                <p className="page-description">
                    All 50 AI agents in the default simulation
                </p>
                <p className="agent-identity-note" title={AGENT_ALIAS_HELP_TEXT}>
                    Aliases are immutable codenames. Canonical identity is Agent #NN.
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
                        <option value="1">Tier 1</option>
                        <option value="2">Tier 2</option>
                        <option value="3">Tier 3</option>
                        <option value="4">Tier 4</option>
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
                {loading ? 'Loading agents…' : `Showing ${filteredAgents.length} of ${agents.length} agents`}
            </div>

            {/* Agent Grid */}
            <div className="agent-grid">
                {!loading && filteredAgents.length === 0 && (
                    <div className="empty-state" style={{ gridColumn: '1 / -1' }}>
                        No agents found.
                    </div>
                )}

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
                                    <h4>{formatAgentDisplayLabel(agent)}</h4>
                                    <span className="agent-model">{modelNames[agent.model_type] || agent.model_type}</span>
                                </div>
                                <span className={`badge badge-${agent.status}`}>
                                    {agent.status}
                                </span>
                            </div>

                            <div className="agent-meta">
                                <span className={`badge badge-tier-${agent.tier}`}>Tier {agent.tier}</span>
                                <PersonalityBadge personality={agent.personality_type} showIcon={false} />
                            </div>

                            <div className="agent-stats" style={{ gridTemplateColumns: '1fr', textAlign: 'left' }}>
                                <div className="agent-stat">
                                    <div className="agent-stat-label" style={{ marginBottom: 0 }}>
                                        Last active
                                    </div>
                                    <div className="agent-stat-value" style={{ fontSize: '0.875rem', fontWeight: 500 }}>
                                        {agent.last_active_at
                                            ? formatDistanceToNow(new Date(agent.last_active_at), { addSuffix: true })
                                            : '—'}
                                    </div>
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

        .agent-identity-note {
          margin-top: var(--spacing-xs);
          color: var(--text-muted);
          font-size: 0.75rem;
        }
      `}</style>
        </div>
    )
}
