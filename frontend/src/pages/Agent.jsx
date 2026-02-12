import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import {
    User,
    ArrowLeft,
    MessageSquare,
    FileText,
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
                    <div className="agent-profile-actions">
                        <SubscribeButton agent={agent} size="medium" />
                    </div>
                </div>
            </div>

            {/* Inventory */}
            <div className="stats-grid" style={{ marginBottom: 'var(--spacing-xl)' }}>
                {agent.inventory.map(inv => (
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
