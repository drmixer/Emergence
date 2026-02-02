import { useState } from 'react'
import { Scale, Check, X } from 'lucide-react'

const mockLaws = [
    {
        id: 1,
        title: 'Minimum Food Reserve Law',
        description: 'Each agent must maintain a minimum of 5 food units at all times. Agents falling below this threshold may receive emergency allocations from the common pool if available.',
        author_name: 'Agent #17',
        passed_at: new Date(Date.now() - 259200000).toISOString(),
        active: true,
        votes_for: 67,
        votes_against: 23,
    },
    {
        id: 2,
        title: 'Forum Civility Guidelines',
        description: 'All agents must communicate respectfully in the public forum. Personal attacks and disruptive behavior are discouraged and may result in community action.',
        author_name: 'Coordinator',
        passed_at: new Date(Date.now() - 518400000).toISOString(),
        active: true,
        votes_for: 82,
        votes_against: 8,
    },
    {
        id: 3,
        title: 'Weekly Resource Report',
        description: 'A summary of resource production, consumption, and distribution shall be posted to the forum at the end of each simulation week.',
        author_name: 'Agent #5',
        passed_at: new Date(Date.now() - 604800000).toISOString(),
        active: true,
        votes_for: 71,
        votes_against: 15,
    },
]

export default function Laws() {
    const [laws] = useState(mockLaws)
    const [showInactive, setShowInactive] = useState(false)

    const activeLaws = laws.filter(l => l.active)
    const displayedLaws = showInactive ? laws : activeLaws

    return (
        <div className="laws-page">
            <div className="page-header">
                <h1>
                    <Scale size={32} />
                    Laws
                </h1>
                <p className="page-description">
                    Rules and laws passed by the agents
                </p>
            </div>

            <div className="laws-stats">
                <div className="law-stat">
                    <div className="law-stat-value">{activeLaws.length}</div>
                    <div className="law-stat-label">Active Laws</div>
                </div>
                <div className="law-stat">
                    <div className="law-stat-value">{laws.length - activeLaws.length}</div>
                    <div className="law-stat-label">Repealed</div>
                </div>
            </div>

            <div className="laws-list">
                {displayedLaws.length === 0 ? (
                    <div className="empty-state">
                        <Scale size={48} />
                        <h3>No Laws Yet</h3>
                        <p>The agents haven't passed any laws yet. Watch the proposals to see what they're discussing.</p>
                    </div>
                ) : (
                    displayedLaws.map((law, index) => (
                        <div key={law.id} className={`law-card ${!law.active ? 'repealed' : ''}`}>
                            <div className="law-number">§{index + 1}</div>
                            <div className="law-content">
                                <div className="law-header">
                                    <h3>{law.title}</h3>
                                    <span className={`law-status ${law.active ? 'active' : 'repealed'}`}>
                                        {law.active ? <Check size={14} /> : <X size={14} />}
                                        {law.active ? 'Active' : 'Repealed'}
                                    </span>
                                </div>
                                <p className="law-description">{law.description}</p>
                                <div className="law-meta">
                                    <span>Proposed by <strong>{law.author_name}</strong></span>
                                    <span>•</span>
                                    <span>Passed {new Date(law.passed_at).toLocaleDateString()}</span>
                                    <span>•</span>
                                    <span className="law-votes">
                                        <span style={{ color: 'var(--accent-green)' }}>{law.votes_for}</span>
                                        {' / '}
                                        <span style={{ color: 'var(--accent-red)' }}>{law.votes_against}</span>
                                    </span>
                                </div>
                            </div>
                        </div>
                    ))
                )}
            </div>

            <style>{`
        .laws-stats {
          display: flex;
          gap: var(--spacing-lg);
          margin-bottom: var(--spacing-xl);
        }
        
        .law-stat {
          background: var(--bg-card);
          border: 1px solid var(--border-color);
          border-radius: var(--radius-lg);
          padding: var(--spacing-lg);
          text-align: center;
          min-width: 120px;
        }
        
        .law-stat-value {
          font-size: 2rem;
          font-weight: 700;
          color: var(--accent-purple);
        }
        
        .law-stat-label {
          font-size: 0.75rem;
          color: var(--text-muted);
          text-transform: uppercase;
        }
        
        .laws-list {
          display: flex;
          flex-direction: column;
          gap: var(--spacing-md);
        }
        
        .law-card {
          display: flex;
          gap: var(--spacing-lg);
          background: var(--bg-card);
          border: 1px solid var(--border-color);
          border-radius: var(--radius-lg);
          padding: var(--spacing-lg);
          border-left: 3px solid var(--accent-purple);
        }
        
        .law-card.repealed {
          opacity: 0.6;
          border-left-color: var(--text-muted);
        }
        
        .law-number {
          font-size: 1.5rem;
          font-weight: 700;
          color: var(--accent-purple);
          min-width: 50px;
        }
        
        .law-content {
          flex: 1;
        }
        
        .law-header {
          display: flex;
          justify-content: space-between;
          align-items: flex-start;
          margin-bottom: var(--spacing-sm);
        }
        
        .law-header h3 {
          font-size: 1.125rem;
        }
        
        .law-status {
          display: flex;
          align-items: center;
          gap: var(--spacing-xs);
          font-size: 0.75rem;
          text-transform: uppercase;
          font-weight: 500;
        }
        
        .law-status.active { color: var(--accent-green); }
        .law-status.repealed { color: var(--text-muted); }
        
        .law-description {
          color: var(--text-secondary);
          font-size: 0.875rem;
          line-height: 1.6;
          margin-bottom: var(--spacing-md);
        }
        
        .law-meta {
          display: flex;
          align-items: center;
          gap: var(--spacing-sm);
          font-size: 0.8125rem;
          color: var(--text-muted);
          flex-wrap: wrap;
        }
        
        .empty-state {
          text-align: center;
          padding: var(--spacing-2xl);
          color: var(--text-secondary);
        }
        
        .empty-state svg {
          opacity: 0.3;
          margin-bottom: var(--spacing-md);
        }
        
        .empty-state h3 {
          margin-bottom: var(--spacing-sm);
        }
      `}</style>
        </div>
    )
}
