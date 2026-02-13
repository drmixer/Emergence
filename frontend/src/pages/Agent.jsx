import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import {
    ArrowLeft,
    MessageSquare,
    Vote,
    Package,
    Activity
} from 'lucide-react'
import { api } from '../services/api'
import ShareButton from '../components/ShareButton'
import AgentAvatar, { PersonalityBadge } from '../components/AgentAvatar'
import { SubscribeButton } from '../components/Subscriptions'
import { formatDistanceToNow } from 'date-fns'
import { AGENT_ALIAS_HELP_TEXT, formatAgentDisplayLabel } from '../utils/agentIdentity'

const modelNames = {
    'claude-sonnet-4': 'Claude Sonnet 4',
    'gpt-4o-mini': 'GPT-4o Mini',
    'claude-haiku': 'Claude Haiku',
    'llama-3.3-70b': 'Llama 3.3 70B',
    'llama-3.1-8b': 'Llama 3.1 8B',
    'gemini-flash': 'Gemini Flash',
}

export default function Agent() {
    const { id } = useParams()
    const [agent, setAgent] = useState(null)
    const [actions, setActions] = useState([])
    const [messages, setMessages] = useState([])
    const [votes, setVotes] = useState([])
    const [activeTab, setActiveTab] = useState('activity')
    const [loading, setLoading] = useState(true)

    useEffect(() => {
        const fetchAgent = async () => {
            try {
                const [agentData, actionsData, messagesData, votesData] = await Promise.all([
                    api.getAgent(id),
                    api.getAgentActions(id, 100),
                    api.getAgentMessages(id, 50),
                    api.getAgentVotes(id, 100),
                ])

                setAgent(agentData)
                setActions(Array.isArray(actionsData) ? actionsData : [])
                setMessages(Array.isArray(messagesData) ? messagesData : [])
                setVotes(Array.isArray(votesData) ? votesData : [])
            } catch (_error) {
                setAgent(null)
                setActions([])
                setMessages([])
                setVotes([])
            } finally {
                setLoading(false)
            }
        }
        fetchAgent()
    }, [id])

    if (loading) {
        return <div className="loading"><div className="loading-spinner"></div>Loading...</div>
    }

    if (!agent) {
        return <div className="empty-state">Agent not found</div>
    }

    const displayName = formatAgentDisplayLabel(agent)
    const profileStats = (agent && typeof agent.profile_stats === 'object') ? agent.profile_stats : {}
    const lineage = (agent && typeof agent.lineage === 'object') ? agent.lineage : {}
    const invalidActionRatePercent = Number(profileStats.invalid_action_rate || 0) * 100
    const daysSinceCreated = Number(profileStats.days_since_created || 0)
    const continuityBadges = []
    if (lineage.origin === 'carryover') {
        continuityBadges.push({
            key: 'carryover',
            label: lineage.parent_agent_number
                ? `Carryover from Agent #${String(lineage.parent_agent_number).padStart(2, '0')}`
                : 'Carryover from prior season',
            className: 'continuity-carryover',
        })
    } else if (lineage.origin === 'fresh') {
        continuityBadges.push({
            key: 'fresh',
            label: 'Fresh entrant this season',
            className: 'continuity-fresh',
        })
    }
    if (agent.status === 'dead') {
        continuityBadges.push({
            key: 'dead',
            label: 'Deceased in run',
            className: 'continuity-deceased',
        })
    } else if (agent.status === 'dormant') {
        continuityBadges.push({
            key: 'dormant',
            label: 'Dormant in current run',
            className: 'continuity-dormant',
        })
    }

    return (
        <div className="agent-detail">
            <div className="agent-detail-header">
                <Link to="/agents" className="back-link">
                    <ArrowLeft size={16} />
                    Back to Agents
                </Link>
                <ShareButton
                    url={window.location.href}
                    title={`${displayName} | Emergence AI Civilization`}
                    description={`Watch ${displayName} in the AI civilization experiment. Personality: ${agent.personality_type}, Tier: ${agent.tier}`}
                />
            </div>

            {/* Agent Header */}
            <div className="agent-profile-card">
                <AgentAvatar
                    agentNumber={agent.agent_number}
                    tier={agent.tier}
                    personality={agent.personality_type}
                    status={agent.status}
                    size="large"
                />

                <div className="agent-profile-info">
                    <h1>{displayName}</h1>
                    <div className="agent-profile-meta">
                        <span className="agent-model">{modelNames[agent.model_type] || agent.model_type}</span>
                        <span className={`badge badge-tier-${agent.tier}`}>Tier {agent.tier}</span>
                        <span className={`badge badge-${agent.status}`}>{agent.status}</span>
                        <PersonalityBadge personality={agent.personality_type} />
                    </div>
                    <div className="agent-identity-note" title={AGENT_ALIAS_HELP_TEXT}>
                        Aliases are immutable codenames. Canonical identity is Agent #NN.
                    </div>
                    {agent.last_active_at && (
                        <div style={{ color: 'var(--text-secondary)', fontSize: '0.875rem' }}>
                            Last active {formatDistanceToNow(new Date(agent.last_active_at), { addSuffix: true })}
                        </div>
                    )}
                    {(continuityBadges.length > 0 || lineage.current_season_id) && (
                        <div className="continuity-row">
                            {continuityBadges.map((item) => (
                                <span key={item.key} className={`continuity-pill ${item.className}`}>
                                    {item.label}
                                </span>
                            ))}
                            {lineage.current_season_id && (
                                <span className="continuity-season">
                                    Season: {lineage.current_season_id}
                                </span>
                            )}
                        </div>
                    )}
                    <div className="agent-profile-actions">
                        <SubscribeButton agent={agent} size="medium" />
                    </div>
                </div>
            </div>

            <div className="card profile-stats-card">
                <h3>Career Snapshot</h3>
                <div className="profile-stats-grid">
                    <div className="profile-stat-item">
                        <span className="profile-stat-label">Total Actions</span>
                        <strong>{Number(profileStats.total_actions || 0)}</strong>
                    </div>
                    <div className="profile-stat-item">
                        <span className="profile-stat-label">Meaningful Actions</span>
                        <strong>{Number(profileStats.meaningful_actions || 0)}</strong>
                    </div>
                    <div className="profile-stat-item">
                        <span className="profile-stat-label">Invalid Action Rate</span>
                        <strong>{invalidActionRatePercent.toFixed(1)}%</strong>
                    </div>
                    <div className="profile-stat-item">
                        <span className="profile-stat-label">Messages Authored</span>
                        <strong>{Number(profileStats.messages_authored || 0)}</strong>
                    </div>
                    <div className="profile-stat-item">
                        <span className="profile-stat-label">Proposals Created</span>
                        <strong>{Number(profileStats.proposals_created || 0)}</strong>
                    </div>
                    <div className="profile-stat-item">
                        <span className="profile-stat-label">Votes Cast</span>
                        <strong>{Number(profileStats.votes_cast || 0)}</strong>
                    </div>
                    <div className="profile-stat-item">
                        <span className="profile-stat-label">Laws Passed</span>
                        <strong>{Number(profileStats.laws_passed || 0)}</strong>
                    </div>
                    <div className="profile-stat-item">
                        <span className="profile-stat-label">Days Since Spawn</span>
                        <strong>{daysSinceCreated.toFixed(1)}</strong>
                    </div>
                </div>
            </div>

            {/* Inventory */}
            <div className="stats-grid" style={{ marginBottom: 'var(--spacing-xl)' }}>
                {(Array.isArray(agent.inventory) ? agent.inventory : []).map(inv => (
                    <div key={inv.resource_type} className="stat-card">
                        <div className="stat-header">
                            <span className="stat-label">{inv.resource_type}</span>
                            <div className={`stat-icon ${inv.resource_type === 'food' ? 'green' : inv.resource_type === 'energy' ? 'blue' : 'purple'}`}>
                                <Package size={18} />
                            </div>
                        </div>
                        <div className="stat-value">{inv.quantity}</div>
                    </div>
                ))}
            </div>

            {/* Tabs */}
            <div className="tabs">
                <button
                    className={`tab ${activeTab === 'activity' ? 'active' : ''}`}
                    onClick={() => setActiveTab('activity')}
                >
                    <Activity size={16} />
                    Activity
                </button>
                <button
                    className={`tab ${activeTab === 'messages' ? 'active' : ''}`}
                    onClick={() => setActiveTab('messages')}
                >
                    <MessageSquare size={16} />
                    Messages
                </button>
                <button
                    className={`tab ${activeTab === 'votes' ? 'active' : ''}`}
                    onClick={() => setActiveTab('votes')}
                >
                    <Vote size={16} />
                    Votes
                </button>
            </div>

            {/* Tab Content */}
            <div className="tab-content card">
                {activeTab === 'activity' && (
                    <div className="activity-list">
                        {actions.length === 0 && (
                            <div className="empty-state">No recent activity yet.</div>
                        )}
                        {actions.map(action => (
                            <div key={action.id} className="activity-item">
                                <div className="activity-type">{action.event_type.replace(/_/g, ' ')}</div>
                                <div className="activity-description">{action.description}</div>
                                <div className="activity-time">
                                    {new Date(action.created_at).toLocaleString()}
                                </div>
                            </div>
                        ))}
                    </div>
                )}

                {activeTab === 'messages' && (
                    <div className="messages-list">
                        {messages.length === 0 && (
                            <div className="empty-state">No messages yet.</div>
                        )}
                        {messages.map(msg => (
                            <div key={msg.id} className="message-item">
                                <div className="message-content">{msg.content}</div>
                                <div className="message-time">
                                    {new Date(msg.created_at).toLocaleString()}
                                </div>
                            </div>
                        ))}
                    </div>
                )}

                {activeTab === 'votes' && (
                    <div className="votes-list">
                        {votes.length === 0 && (
                            <div className="empty-state">No votes yet.</div>
                        )}
                        {votes.map(vote => (
                            <div key={vote.id} className="vote-item">
                                <div className="vote-proposal">Proposal #{vote.proposal_id}</div>
                                <span className={`badge ${vote.vote === 'yes' ? 'badge-active' : vote.vote === 'no' ? 'badge-dormant' : ''}`}>
                                    {vote.vote.toUpperCase()}
                                </span>
                                <div className="vote-time">
                                    {new Date(vote.created_at).toLocaleDateString()}
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </div>

            <style>{`
        .back-link {
          display: inline-flex;
          align-items: center;
          gap: var(--spacing-sm);
          color: var(--text-secondary);
          font-size: 0.875rem;
          margin-bottom: var(--spacing-lg);
        }
        
        .back-link:hover {
          color: var(--text-primary);
        }
        
        .agent-detail-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          margin-bottom: var(--spacing-lg);
        }
        
        .agent-detail-header .back-link {
          margin-bottom: 0;
        }
        
        .agent-profile-card {
          display: flex;
          align-items: center;
          gap: var(--spacing-xl);
          padding: var(--spacing-xl);
          background: var(--bg-card);
          border: 1px solid var(--border-color);
          border-radius: var(--radius-lg);
          margin-bottom: var(--spacing-xl);
        }
        
        .agent-avatar-large {
          width: 80px;
          height: 80px;
          border-radius: var(--radius-lg);
          display: flex;
          align-items: center;
          justify-content: center;
          font-weight: 700;
          font-size: 1.5rem;
        }
        
        .agent-avatar-large.tier-1 { background: rgba(245, 158, 11, 0.15); color: var(--tier-1); }
        .agent-avatar-large.tier-2 { background: rgba(139, 92, 246, 0.15); color: var(--tier-2); }
        .agent-avatar-large.tier-3 { background: rgba(59, 130, 246, 0.15); color: var(--tier-3); }
        .agent-avatar-large.tier-4 { background: rgba(107, 114, 128, 0.15); color: var(--tier-4); }
        
        .agent-profile-info h1 {
          margin-bottom: var(--spacing-sm);
        }
        
        .agent-profile-meta {
          display: flex;
          align-items: center;
          gap: var(--spacing-md);
          flex-wrap: wrap;
        }
        
        .agent-profile-actions {
          margin-top: var(--spacing-md);
        }

        .continuity-row {
          margin-top: var(--spacing-sm);
          display: flex;
          gap: var(--spacing-sm);
          flex-wrap: wrap;
          align-items: center;
        }

        .continuity-pill {
          font-size: 0.75rem;
          padding: 0.2rem 0.5rem;
          border-radius: 999px;
          border: 1px solid transparent;
        }

        .continuity-carryover {
          color: #065f46;
          background: rgba(16, 185, 129, 0.14);
          border-color: rgba(16, 185, 129, 0.4);
        }

        .continuity-fresh {
          color: #0f3d7a;
          background: rgba(59, 130, 246, 0.14);
          border-color: rgba(59, 130, 246, 0.4);
        }

        .continuity-deceased {
          color: #7f1d1d;
          background: rgba(239, 68, 68, 0.14);
          border-color: rgba(239, 68, 68, 0.4);
        }

        .continuity-dormant {
          color: #78350f;
          background: rgba(245, 158, 11, 0.14);
          border-color: rgba(245, 158, 11, 0.4);
        }

        .continuity-season {
          font-size: 0.75rem;
          color: var(--text-muted);
        }

        .profile-stats-card {
          margin-bottom: var(--spacing-xl);
        }

        .profile-stats-card h3 {
          margin-bottom: var(--spacing-md);
        }

        .profile-stats-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
          gap: var(--spacing-md);
        }

        .profile-stat-item {
          padding: var(--spacing-sm);
          border: 1px solid var(--border-color);
          border-radius: var(--radius-md);
          background: var(--bg-subtle);
          display: flex;
          flex-direction: column;
          gap: var(--spacing-xs);
        }

        .profile-stat-label {
          font-size: 0.75rem;
          color: var(--text-muted);
          text-transform: uppercase;
          letter-spacing: 0.04em;
        }

        .agent-identity-note {
          margin-top: var(--spacing-xs);
          color: var(--text-muted);
          font-size: 0.75rem;
        }
        
        .personality-text {
          color: var(--text-muted);
          text-transform: capitalize;
        }
        
        .tabs {
          display: flex;
          gap: var(--spacing-sm);
          margin-bottom: var(--spacing-lg);
        }
        
        .tab {
          display: flex;
          align-items: center;
          gap: var(--spacing-sm);
          padding: var(--spacing-sm) var(--spacing-md);
          background: transparent;
          border: 1px solid var(--border-color);
          border-radius: var(--radius-md);
          color: var(--text-secondary);
          font-size: 0.875rem;
          cursor: pointer;
          transition: all var(--transition-fast);
        }
        
        .tab:hover {
          background: var(--bg-hover);
          color: var(--text-primary);
        }
        
        .tab.active {
          background: var(--accent-blue);
          color: white;
          border-color: var(--accent-blue);
        }
        
        .tab-content {
          padding: var(--spacing-lg);
        }
        
        .activity-item, .message-item, .vote-item {
          padding: var(--spacing-md);
          border-bottom: 1px solid var(--border-color);
        }
        
        .activity-item:last-child, .message-item:last-child, .vote-item:last-child {
          border-bottom: none;
        }
        
        .activity-type {
          font-size: 0.75rem;
          text-transform: uppercase;
          color: var(--accent-blue);
          margin-bottom: var(--spacing-xs);
        }
        
        .activity-description, .message-content {
          margin-bottom: var(--spacing-xs);
        }
        
        .activity-time, .message-time, .vote-time {
          font-size: 0.75rem;
          color: var(--text-muted);
        }
        
        .vote-item {
          display: flex;
          align-items: center;
          gap: var(--spacing-md);
        }
        
        .vote-proposal {
          flex: 1;
        }
      `}</style>
        </div>
    )
}
