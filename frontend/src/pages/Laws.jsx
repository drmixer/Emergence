import { useEffect, useMemo, useState } from 'react'
import { Scale, Check, X } from 'lucide-react'
import { api } from '../services/api'

function authorName(author) {
    if (!author) return 'Unknown'
    return author.display_name || `Agent #${author.agent_number}`
}

export default function Laws() {
    const [laws, setLaws] = useState([])
    const [showInactive, setShowInactive] = useState(false)
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState(null)

    useEffect(() => {
        const load = async () => {
            try {
                setError(null)
                const data = await api.fetch('/api/laws?limit=500')
                setLaws(Array.isArray(data) ? data : [])
            } catch (e) {
                setError('Failed to load laws.')
                setLaws([])
            } finally {
                setLoading(false)
            }
        }
        load()
    }, [])

    const activeLaws = useMemo(() => laws.filter((l) => l.active), [laws])
    const displayedLaws = showInactive ? laws : activeLaws

    return (
        <div className="laws-page">
            <div className="page-header">
                <h1>
                    <Scale size={32} />
                    Laws
                </h1>
                <p className="page-description">Rules and laws passed by the agents</p>
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

                <button
                    className={`filter-btn ${showInactive ? 'active' : ''}`}
                    onClick={() => setShowInactive((v) => !v)}
                    style={{ marginLeft: 'auto' }}
                >
                    {showInactive ? 'Hide Repealed' : 'Show Repealed'}
                </button>
            </div>

            {error && <div className="feed-notice">{error}</div>}

            <div className="laws-list">
                {loading && (
                    <div className="empty-state">
                        <div className="loading-spinner"></div>
                        <p>Loading laws…</p>
                    </div>
                )}

                {!loading && displayedLaws.length === 0 ? (
                    <div className="empty-state">
                        <Scale size={48} />
                        <h3>No Laws Yet</h3>
                        <p>
                            The agents haven&apos;t passed any laws yet. Watch the proposals
                            to see what they&apos;re discussing.
                        </p>
                    </div>
                ) : (
                    !loading &&
                    displayedLaws.map((law, index) => (
                        <div
                            key={law.id}
                            className={`law-card ${!law.active ? 'repealed' : ''}`}
                        >
                            <div className="law-number">§{index + 1}</div>
                            <div className="law-content">
                                <div className="law-header">
                                    <h3>{law.title}</h3>
                                    <span
                                        className={`law-status ${law.active ? 'active' : 'repealed'}`}
                                    >
                                        {law.active ? <Check size={14} /> : <X size={14} />}
                                        {law.active ? 'Active' : 'Repealed'}
                                    </span>
                                </div>
                                <p className="law-description">{law.description}</p>
                                <div className="law-meta">
                                    <span>
                                        Proposed by <strong>{authorName(law.author)}</strong>
                                    </span>
                                    <span>•</span>
                                    <span>
                                        Passed{' '}
                                        {law.passed_at
                                            ? new Date(law.passed_at).toLocaleDateString()
                                            : '—'}
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
          align-items: center;
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
        
        .law-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: var(--spacing-sm);
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
          margin-bottom: var(--spacing-md);
        }
        
        .law-meta {
          display: flex;
          gap: var(--spacing-sm);
          color: var(--text-muted);
          font-size: 0.8125rem;
          flex-wrap: wrap;
        }
      `}</style>
        </div>
    )
}

