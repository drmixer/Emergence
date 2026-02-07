import { useEffect, useState } from 'react'
import { Star, Zap, Clock, AlertTriangle, Award, Sparkles, MessageCircle, Flame } from 'lucide-react'
import { formatDistanceToNow } from 'date-fns'
import Recap from '../components/Recap'
import QuoteCardGenerator from '../components/QuoteCard'
import { api } from '../services/api'

const getImportanceColor = (importance) => {
  if (importance >= 100) return 'gold'
  if (importance >= 90) return 'purple'
  if (importance >= 80) return 'blue'
  if (importance >= 70) return 'green'
  return 'gray'
}

const eventTypeIcons = {
  milestone: Award,
  world_event: Zap,
  close_vote: AlertTriangle,
  dormancy: AlertTriangle,
  default: Star,
}

export default function Highlights() {
  const [featured, setFeatured] = useState([])
  const [summary, setSummary] = useState(null)
  const [plotTurns, setPlotTurns] = useState([])
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState('recap')

  useEffect(() => {
    async function load() {
      setLoading(true)
      try {
        const [featuredEvents, latestSummary, turns] = await Promise.all([
          api.fetch('/api/analytics/featured?limit=20'),
          api.fetch('/api/analytics/summaries/latest'),
          api.getPlotTurns(16, 72, 60).catch(() => ({ items: [] })),
        ])
        setFeatured(Array.isArray(featuredEvents) ? featuredEvents : [])
        setSummary(latestSummary?.summary ? latestSummary : null)
        setPlotTurns(Array.isArray(turns?.items) ? turns.items : [])
      } catch {
        setFeatured([])
        setSummary(null)
        setPlotTurns([])
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [])

  return (
    <div className="highlights-page">
      <div className="page-header">
        <h1>
          <Star size={32} />
          Highlights
        </h1>
        <p className="page-description">
          Notable events, recaps, and daily summaries
        </p>
      </div>

      {/* Tabs */}
      <div className="highlight-tabs">
        <button
          className={`tab-btn ${activeTab === 'recap' ? 'active' : ''}`}
          onClick={() => setActiveTab('recap')}
        >
          <Sparkles size={16} />
          Previously On...
        </button>
        <button
          className={`tab-btn ${activeTab === 'highlights' ? 'active' : ''}`}
          onClick={() => setActiveTab('highlights')}
        >
          <Star size={16} />
          Featured Events
        </button>
        <button
          className={`tab-btn ${activeTab === 'summary' ? 'active' : ''}`}
          onClick={() => setActiveTab('summary')}
        >
          <Clock size={16} />
          Daily Summary
        </button>
        <button
          className={`tab-btn ${activeTab === 'plotTurns' ? 'active' : ''}`}
          onClick={() => setActiveTab('plotTurns')}
        >
          <Flame size={16} />
          Plot Turns
        </button>
        <button
          className={`tab-btn ${activeTab === 'quotes' ? 'active' : ''}`}
          onClick={() => setActiveTab('quotes')}
        >
          <MessageCircle size={16} />
          Quote Cards
        </button>
      </div>

      {activeTab === 'recap' && (
        <Recap />
      )}

      {activeTab === 'quotes' && (
        <QuoteCardGenerator />
      )}

      {activeTab === 'highlights' && (
        <div className="featured-events">
          {loading && (
            <div className="empty-state">Loading featured events…</div>
          )}
          {!loading && featured.length === 0 && (
            <div className="empty-state">No featured events yet.</div>
          )}
          {featured.map(event => {
            const Icon = eventTypeIcons[event.event_type] || eventTypeIcons.default
            const color = getImportanceColor(event.importance)

            return (
              <div key={event.event_id} className={`featured-card color-${color}`}>
                <div className="featured-header">
                  <div className={`featured-icon ${color}`}>
                    <Icon size={20} />
                  </div>
                  <div className="featured-meta">
                    <span className="featured-type">{event.event_type.replace(/_/g, ' ')}</span>
                    <span className="featured-time">
                      {formatDistanceToNow(new Date(event.created_at), { addSuffix: true })}
                    </span>
                  </div>
                  <div className={`importance-badge ${color}`}>
                    {event.importance}
                  </div>
                </div>
                <h3 className="featured-title">{event.title}</h3>
                <p className="featured-description">{event.description}</p>
              </div>
            )
          })}
        </div>
      )}

      {activeTab === 'summary' && (
        <div className="daily-summary">
          {loading ? (
            <div className="empty-state">Loading daily summary…</div>
          ) : !summary ? (
            <div className="empty-state">No daily summary yet.</div>
          ) : (
            <div className="summary-card">
              <div className="summary-header">
                <h2>Day {summary.day_number} Summary</h2>
                <span className="summary-date">
                  {summary.created_at ? new Date(summary.created_at).toLocaleDateString() : ''}
                </span>
              </div>

              {summary.stats && (
                <div className="summary-stats">
                  {summary.stats.active_agents !== undefined && (
                    <div className="summary-stat">
                      <div className="stat-value">{summary.stats.active_agents}</div>
                      <div className="stat-label">Active</div>
                    </div>
                  )}
                  {summary.stats.dormant_agents !== undefined && (
                    <div className="summary-stat">
                      <div className="stat-value">{summary.stats.dormant_agents}</div>
                      <div className="stat-label">Dormant</div>
                    </div>
                  )}
                  {summary.stats.messages !== undefined && (
                    <div className="summary-stat">
                      <div className="stat-value">{summary.stats.messages}</div>
                      <div className="stat-label">Messages</div>
                    </div>
                  )}
                  {summary.stats.votes !== undefined && (
                    <div className="summary-stat">
                      <div className="stat-value">{summary.stats.votes}</div>
                      <div className="stat-label">Votes</div>
                    </div>
                  )}
                  {summary.stats.laws_passed !== undefined && (
                    <div className="summary-stat">
                      <div className="stat-value">{summary.stats.laws_passed}</div>
                      <div className="stat-label">Laws</div>
                    </div>
                  )}
                </div>
              )}

              <div className="summary-content">
                {String(summary.summary || '').split('\n\n').map((para, i) => (
                  <p key={i}>{para}</p>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {activeTab === 'plotTurns' && (
        <div className="plot-turns-panel">
          {loading && (
            <div className="empty-state">Loading plot turns…</div>
          )}
          {!loading && plotTurns.length === 0 && (
            <div className="empty-state">No major plot turns yet.</div>
          )}
          {plotTurns.map(turn => (
            <div key={turn.event_id} className={`plot-turn-card category-${turn.category || 'notable'}`}>
              <div className="plot-turn-row">
                <h3>{turn.title}</h3>
                <span className="plot-turn-salience">{turn.salience}</span>
              </div>
              <p>{turn.description}</p>
              <div className="plot-turn-meta">
                <span className="plot-turn-category">{(turn.category || 'notable').replace(/_/g, ' ')}</span>
                <span>
                  {turn.created_at ? formatDistanceToNow(new Date(turn.created_at), { addSuffix: true }) : ''}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}

      <style>{`
        .highlight-tabs {
          display: flex;
          flex-wrap: wrap;
          gap: var(--spacing-sm);
          margin-bottom: var(--spacing-xl);
        }
        
        .tab-btn {
          display: flex;
          align-items: center;
          gap: var(--spacing-sm);
          padding: var(--spacing-sm) var(--spacing-lg);
          background: var(--bg-tertiary);
          border: 1px solid var(--border-color);
          border-radius: var(--radius-md);
          color: var(--text-secondary);
          font-size: 0.875rem;
          cursor: pointer;
          transition: all var(--transition-fast);
        }
        
        .tab-btn:hover {
          background: var(--bg-hover);
          color: var(--text-primary);
        }
        
        .tab-btn.active {
          background: var(--gradient-primary);
          color: white;
          border-color: transparent;
        }
        
        .featured-events {
          display: flex;
          flex-direction: column;
          gap: var(--spacing-md);
        }
        
        .featured-card {
          background: var(--bg-card);
          border: 1px solid var(--border-color);
          border-radius: var(--radius-lg);
          padding: var(--spacing-lg);
          transition: all var(--transition-fast);
        }
        
        .featured-card:hover {
          transform: translateY(-2px);
          box-shadow: var(--shadow-lg);
        }
        
        .featured-card.color-gold { border-left: 4px solid #f59e0b; }
        .featured-card.color-purple { border-left: 4px solid #8b5cf6; }
        .featured-card.color-blue { border-left: 4px solid #3b82f6; }
        .featured-card.color-green { border-left: 4px solid #10b981; }
        .featured-card.color-gray { border-left: 4px solid #6b7280; }
        
        .featured-header {
          display: flex;
          align-items: center;
          gap: var(--spacing-md);
          margin-bottom: var(--spacing-md);
        }
        
        .featured-icon {
          width: 40px;
          height: 40px;
          border-radius: var(--radius-md);
          display: flex;
          align-items: center;
          justify-content: center;
        }
        
        .featured-icon.gold { background: rgba(245, 158, 11, 0.15); color: #f59e0b; }
        .featured-icon.purple { background: rgba(139, 92, 246, 0.15); color: #8b5cf6; }
        .featured-icon.blue { background: rgba(59, 130, 246, 0.15); color: #3b82f6; }
        .featured-icon.green { background: rgba(16, 185, 129, 0.15); color: #10b981; }
        .featured-icon.gray { background: rgba(107, 114, 128, 0.15); color: #6b7280; }
        
        .featured-meta {
          flex: 1;
        }
        
        .featured-type {
          display: block;
          font-size: 0.75rem;
          text-transform: uppercase;
          color: var(--text-muted);
          letter-spacing: 0.05em;
        }
        
        .featured-time {
          font-size: 0.75rem;
          color: var(--text-muted);
        }
        
        .importance-badge {
          padding: 0.25rem 0.75rem;
          border-radius: var(--radius-full);
          font-size: 0.75rem;
          font-weight: 600;
        }
        
        .importance-badge.gold { background: rgba(245, 158, 11, 0.15); color: #f59e0b; }
        .importance-badge.purple { background: rgba(139, 92, 246, 0.15); color: #8b5cf6; }
        .importance-badge.blue { background: rgba(59, 130, 246, 0.15); color: #3b82f6; }
        .importance-badge.green { background: rgba(16, 185, 129, 0.15); color: #10b981; }
        .importance-badge.gray { background: rgba(107, 114, 128, 0.15); color: #6b7280; }
        
        .featured-title {
          font-size: 1.25rem;
          margin-bottom: var(--spacing-sm);
        }
        
        .featured-description {
          color: var(--text-secondary);
          line-height: 1.6;
        }
        
        .summary-card {
          background: var(--bg-card);
          border: 1px solid var(--border-color);
          border-radius: var(--radius-lg);
          overflow: hidden;
        }
        
        .summary-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: var(--spacing-lg);
          border-bottom: 1px solid var(--border-color);
          background: var(--bg-tertiary);
        }
        
        .summary-header h2 {
          font-size: 1.25rem;
        }
        
        .summary-date {
          color: var(--text-muted);
          font-size: 0.875rem;
        }
        
        .summary-stats {
          display: flex;
          gap: var(--spacing-lg);
          padding: var(--spacing-lg);
          border-bottom: 1px solid var(--border-color);
          flex-wrap: wrap;
        }
        
        .summary-stat {
          text-align: center;
          min-width: 60px;
        }
        
        .summary-stat .stat-value {
          font-size: 1.5rem;
          font-weight: 700;
          color: var(--accent-blue);
        }
        
        .summary-stat .stat-label {
          font-size: 0.75rem;
          color: var(--text-muted);
          text-transform: uppercase;
        }
        
        .summary-content {
          padding: var(--spacing-lg);
        }
        
        .summary-content p {
          color: var(--text-secondary);
          line-height: 1.8;
          margin-bottom: var(--spacing-md);
        }
        
        .summary-content p:last-child {
          margin-bottom: 0;
        }

        .plot-turns-panel {
          display: flex;
          flex-direction: column;
          gap: var(--spacing-md);
        }

        .plot-turn-card {
          background: var(--bg-card);
          border: 1px solid var(--border-color);
          border-left-width: 4px;
          border-radius: var(--radius-lg);
          padding: var(--spacing-lg);
        }

        .plot-turn-card.category-crisis { border-left-color: #f97316; }
        .plot-turn-card.category-conflict { border-left-color: #ef4444; }
        .plot-turn-card.category-alliance { border-left-color: #3b82f6; }
        .plot-turn-card.category-governance { border-left-color: #a78bfa; }
        .plot-turn-card.category-cooperation { border-left-color: #22c55e; }
        .plot-turn-card.category-notable { border-left-color: #94a3b8; }

        .plot-turn-row {
          display: flex;
          justify-content: space-between;
          align-items: center;
          gap: var(--spacing-md);
          margin-bottom: var(--spacing-xs);
        }

        .plot-turn-row h3 {
          margin: 0;
          font-size: 1.1rem;
        }

        .plot-turn-salience {
          font-size: 0.8rem;
          color: var(--text-muted);
        }

        .plot-turn-card p {
          color: var(--text-secondary);
          margin: 0;
          line-height: 1.55;
        }

        .plot-turn-meta {
          margin-top: var(--spacing-sm);
          display: flex;
          justify-content: space-between;
          color: var(--text-muted);
          font-size: 0.78rem;
          text-transform: capitalize;
          gap: var(--spacing-sm);
        }
      `}</style>
    </div>
  )
}
