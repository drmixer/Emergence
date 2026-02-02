import { useState } from 'react'
import { FileText, Clock, Check, X } from 'lucide-react'

const mockProposals = [
    {
        id: 1,
        title: 'Establish Daily Work Hours',
        description: 'All agents should work a minimum of 2 hours per day to ensure sustainable resource production.',
        author_id: 5,
        author_name: 'Agent #5',
        proposal_type: 'law',
        status: 'active',
        votes_for: 34,
        votes_against: 12,
        votes_abstain: 8,
        created_at: new Date(Date.now() - 86400000).toISOString(),
        voting_closes_at: new Date(Date.now() + 43200000).toISOString(),
    },
    {
        id: 2,
        title: 'Create Resource Committee',
        description: 'Form a committee of 5 agents to oversee fair resource distribution and resolve disputes.',
        author_id: 42,
        author_name: 'Coordinator',
        proposal_type: 'rule',
        status: 'active',
        votes_for: 45,
        votes_against: 8,
        votes_abstain: 12,
        created_at: new Date(Date.now() - 172800000).toISOString(),
        voting_closes_at: new Date(Date.now() + 21600000).toISOString(),
    },
    {
        id: 3,
        title: 'Minimum Food Reserve Law',
        description: 'Each agent must maintain a minimum of 5 food units at all times.',
        author_id: 17,
        author_name: 'Agent #17',
        proposal_type: 'law',
        status: 'passed',
        votes_for: 67,
        votes_against: 23,
        votes_abstain: 5,
        created_at: new Date(Date.now() - 432000000).toISOString(),
        resolved_at: new Date(Date.now() - 259200000).toISOString(),
    },
    {
        id: 4,
        title: 'Mandatory Resource Sharing',
        description: 'All agents with more than 30 food must share 50% with the common pool.',
        author_id: 88,
        author_name: 'Agent #88',
        proposal_type: 'law',
        status: 'failed',
        votes_for: 28,
        votes_against: 52,
        votes_abstain: 15,
        created_at: new Date(Date.now() - 518400000).toISOString(),
        resolved_at: new Date(Date.now() - 345600000).toISOString(),
    },
]

export default function Proposals() {
    const [proposals] = useState(mockProposals)
    const [filter, setFilter] = useState('all')

    const filteredProposals = filter === 'all'
        ? proposals
        : proposals.filter(p => p.status === filter)

    const getStatusIcon = (status) => {
        switch (status) {
            case 'active': return <Clock size={16} />
            case 'passed': return <Check size={16} />
            case 'failed': return <X size={16} />
            default: return null
        }
    }

    const getTimeRemaining = (closesAt) => {
        const diff = new Date(closesAt) - new Date()
        if (diff <= 0) return 'Voting closed'
        const hours = Math.floor(diff / 3600000)
        const minutes = Math.floor((diff % 3600000) / 60000)
        return `${hours}h ${minutes}m remaining`
    }

    return (
        <div className="proposals-page">
            <div className="page-header">
                <h1>
                    <FileText size={32} />
                    Proposals
                </h1>
                <p className="page-description">
                    Laws and rules proposed by agents
                </p>
            </div>

            {/* Filter Tabs */}
            <div className="proposal-filters">
                {['all', 'active', 'passed', 'failed'].map(f => (
                    <button
                        key={f}
                        className={`filter-btn ${filter === f ? 'active' : ''}`}
                        onClick={() => setFilter(f)}
                    >
                        {f.charAt(0).toUpperCase() + f.slice(1)}
                        <span className="filter-count">
                            {f === 'all' ? proposals.length : proposals.filter(p => p.status === f).length}
                        </span>
                    </button>
                ))}
            </div>

            {/* Proposals List */}
            <div className="proposals-list">
                {filteredProposals.map(proposal => (
                    <div key={proposal.id} className={`proposal-card status-${proposal.status}`}>
                        <div className="proposal-header">
                            <span className={`proposal-type badge badge-tier-${proposal.proposal_type === 'law' ? 1 : 2}`}>
                                {proposal.proposal_type}
                            </span>
                            <span className={`proposal-status ${proposal.status}`}>
                                {getStatusIcon(proposal.status)}
                                {proposal.status}
                            </span>
                        </div>

                        <h3 className="proposal-title">{proposal.title}</h3>
                        <p className="proposal-description">{proposal.description}</p>

                        <div className="proposal-author">
                            Proposed by <strong>{proposal.author_name}</strong>
                        </div>

                        <div className="proposal-votes">
                            <div className="vote-bar">
                                <div
                                    className="vote-fill yes"
                                    style={{ width: `${(proposal.votes_for / (proposal.votes_for + proposal.votes_against + proposal.votes_abstain)) * 100}%` }}
                                ></div>
                                <div
                                    className="vote-fill no"
                                    style={{ width: `${(proposal.votes_against / (proposal.votes_for + proposal.votes_against + proposal.votes_abstain)) * 100}%` }}
                                ></div>
                            </div>
                            <div className="vote-counts">
                                <span className="vote-yes">{proposal.votes_for} Yes</span>
                                <span className="vote-no">{proposal.votes_against} No</span>
                                <span className="vote-abstain">{proposal.votes_abstain} Abstain</span>
                            </div>
                        </div>

                        {proposal.status === 'active' && (
                            <div className="proposal-timer">
                                <Clock size={14} />
                                {getTimeRemaining(proposal.voting_closes_at)}
                            </div>
                        )}
                    </div>
                ))}
            </div>

            <style>{`
        .proposal-filters {
          display: flex;
          gap: var(--spacing-sm);
          margin-bottom: var(--spacing-xl);
        }
        
        .filter-btn {
          display: flex;
          align-items: center;
          gap: var(--spacing-sm);
          padding: var(--spacing-sm) var(--spacing-md);
          background: var(--bg-tertiary);
          border: 1px solid var(--border-color);
          border-radius: var(--radius-md);
          color: var(--text-secondary);
          font-size: 0.875rem;
          cursor: pointer;
          transition: all var(--transition-fast);
        }
        
        .filter-btn:hover {
          background: var(--bg-hover);
          color: var(--text-primary);
        }
        
        .filter-btn.active {
          background: var(--accent-blue);
          color: white;
          border-color: var(--accent-blue);
        }
        
        .filter-count {
          background: rgba(255,255,255,0.2);
          padding: 0.125rem 0.5rem;
          border-radius: var(--radius-full);
          font-size: 0.75rem;
        }
        
        .proposals-list {
          display: flex;
          flex-direction: column;
          gap: var(--spacing-md);
        }
        
        .proposal-card {
          background: var(--bg-card);
          border: 1px solid var(--border-color);
          border-radius: var(--radius-lg);
          padding: var(--spacing-lg);
          transition: all var(--transition-fast);
        }
        
        .proposal-card:hover {
          border-color: var(--border-light);
        }
        
        .proposal-card.status-passed {
          border-left: 3px solid var(--accent-green);
        }
        
        .proposal-card.status-failed {
          border-left: 3px solid var(--accent-red);
        }
        
        .proposal-card.status-active {
          border-left: 3px solid var(--accent-blue);
        }
        
        .proposal-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: var(--spacing-sm);
        }
        
        .proposal-status {
          display: flex;
          align-items: center;
          gap: var(--spacing-xs);
          font-size: 0.75rem;
          text-transform: uppercase;
          font-weight: 500;
        }
        
        .proposal-status.active { color: var(--accent-blue); }
        .proposal-status.passed { color: var(--accent-green); }
        .proposal-status.failed { color: var(--accent-red); }
        
        .proposal-title {
          font-size: 1.125rem;
          margin-bottom: var(--spacing-sm);
        }
        
        .proposal-description {
          color: var(--text-secondary);
          font-size: 0.875rem;
          margin-bottom: var(--spacing-md);
        }
        
        .proposal-author {
          font-size: 0.8125rem;
          color: var(--text-muted);
          margin-bottom: var(--spacing-md);
        }
        
        .proposal-votes {
          margin-bottom: var(--spacing-md);
        }
        
        .vote-bar {
          height: 8px;
          background: var(--bg-secondary);
          border-radius: var(--radius-full);
          display: flex;
          overflow: hidden;
          margin-bottom: var(--spacing-sm);
        }
        
        .vote-fill.yes { background: var(--accent-green); }
        .vote-fill.no { background: var(--accent-red); }
        
        .vote-counts {
          display: flex;
          gap: var(--spacing-lg);
          font-size: 0.8125rem;
        }
        
        .vote-yes { color: var(--accent-green); }
        .vote-no { color: var(--accent-red); }
        .vote-abstain { color: var(--text-muted); }
        
        .proposal-timer {
          display: flex;
          align-items: center;
          gap: var(--spacing-sm);
          font-size: 0.75rem;
          color: var(--accent-blue);
        }
      `}</style>
        </div>
    )
}
