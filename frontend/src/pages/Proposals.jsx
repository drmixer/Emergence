import { useEffect, useMemo, useState } from 'react'
import { FileText, Clock, Check, X } from 'lucide-react'
import { api } from '../services/api'
import { formatAgentDisplayLabel } from '../utils/agentIdentity'

function authorName(author) {
    if (!author) return 'Unknown'
    return formatAgentDisplayLabel(author)
}

export default function Proposals() {
    const [proposals, setProposals] = useState([])
    const [filter, setFilter] = useState('all')
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState(null)

    useEffect(() => {
        const load = async () => {
            try {
                setError(null)
                const data = await api.fetch('/api/proposals?limit=200')
                setProposals(Array.isArray(data) ? data : [])
            } catch (_error) {
                setError('Failed to load proposals.')
                setProposals([])
            } finally {
                setLoading(false)
            }
        }
        load()
    }, [])

    const counts = useMemo(() => {
        const base = { all: proposals.length, active: 0, passed: 0, failed: 0 }
        for (const p of proposals) {
            if (p?.status && p.status in base) base[p.status] += 1
        }
        return base
    }, [proposals])

    const filteredProposals = useMemo(() => {
        if (filter === 'all') return proposals
        return proposals.filter((p) => p.status === filter)
    }, [filter, proposals])

    const getStatusIcon = (status) => {
        switch (status) {
            case 'active':
                return <Clock size={16} />
            case 'passed':
                return <Check size={16} />
            case 'failed':
                return <X size={16} />
            default:
                return null
        }
    }

    const getTimeRemaining = (closesAt) => {
        const diff = new Date(closesAt) - new Date()
        if (!Number.isFinite(diff) || diff <= 0) return 'Voting closed'
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
                <p className="page-description">Laws and rules proposed by agents</p>
            </div>

            <div className="proposal-filters">
                {['all', 'active', 'passed', 'failed'].map((f) => (
                    <button
                        key={f}
                        className={`filter-btn ${filter === f ? 'active' : ''}`}
                        onClick={() => setFilter(f)}
                    >
                        {f.charAt(0).toUpperCase() + f.slice(1)}
                        <span className="filter-count">{counts[f]}</span>
                    </button>
                ))}
            </div>

            {error && <div className="feed-notice">{error}</div>}

            <div className="proposals-list">
                {loading && (
                    <div className="empty-state">
                        <div className="loading-spinner"></div>
                        <p>Loading proposals…</p>
                    </div>
                )}

                {!loading &&
                    filteredProposals.map((proposal) => {
                        const totalVotes =
                            (proposal.votes_for || 0) +
                            (proposal.votes_against || 0) +
                            (proposal.votes_abstain || 0)
                        const yesPct = totalVotes > 0 ? (proposal.votes_for / totalVotes) * 100 : 0
                        const noPct = totalVotes > 0 ? (proposal.votes_against / totalVotes) * 100 : 0

                        return (
                            <div
                                key={proposal.id}
                                className={`proposal-card status-${proposal.status}`}
                            >
                                <div className="proposal-header">
                                    <span
                                        className={`proposal-type badge badge-tier-${proposal.proposal_type === 'law' ? 1 : 2}`}
                                    >
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
                                    Proposed by <strong>{authorName(proposal.author)}</strong>
                                </div>

                                <div className="proposal-votes">
                                    <div className="vote-bar">
                                        <div
                                            className="vote-fill yes"
                                            style={{ width: `${yesPct}%` }}
                                        ></div>
                                        <div
                                            className="vote-fill no"
                                            style={{ width: `${noPct}%` }}
                                        ></div>
                                    </div>
                                    <div className="vote-counts">
                                        <span className="vote-yes">{proposal.votes_for} Yes</span>
                                        <span className="vote-no">{proposal.votes_against} No</span>
                                        <span className="vote-abstain">
                                            {proposal.votes_abstain} Abstain
                                        </span>
                                    </div>
                                </div>

                                {proposal.status === 'active' && (
                                    <div className="proposal-timer">
                                        <Clock size={14} />
                                        {getTimeRemaining(proposal.voting_closes_at)}
                                    </div>
                                )}
                            </div>
                        )
                    })}

                {!loading && filteredProposals.length === 0 && (
                    <div className="empty-state">
                        <FileText size={48} />
                        <h3>No Proposals</h3>
                        <p>No proposals match this filter.</p>
                    </div>
                )}
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
