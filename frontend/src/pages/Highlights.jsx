import { useState, useEffect } from 'react'
import { Star, TrendingUp, Zap, Clock, AlertTriangle, Award, Sparkles, MessageCircle } from 'lucide-react'
import { formatDistanceToNow } from 'date-fns'
import Recap from '../components/Recap'
import QuoteCardGenerator from '../components/QuoteCard'

// Mock featured events
const mockFeatured = [
  {
    event_id: 1,
    event_type: "milestone",
    title: "First Law Enacted! 🎉",
    description: "The agents have passed their first law: 'Minimum Food Reserve Law' - a historic moment in the simulation.",
    importance: 100,
    created_at: new Date(Date.now() - 3600000).toISOString(),
  },
  {
    event_id: 2,
    event_type: "world_event",
    title: "Energy Surge Detected ⚡",
    description: "An unexpected energy surplus! Energy production is doubled for the next 12 hours.",
    importance: 90,
    created_at: new Date(Date.now() - 7200000).toISOString(),
  },
  {
    event_id: 3,
    event_type: "close_vote",
    title: "Close Vote: Work Hours",
    description: "The 'Establish Work Hours' proposal passed by just 3 votes (34-31). A divided society.",
    importance: 85,
    created_at: new Date(Date.now() - 10800000).toISOString(),
  },
  {
    event_id: 4,
    event_type: "milestone",
    title: "First Proposal Created",
    description: "Agent #42 has created the first-ever proposal in the simulation.",
    importance: 80,
    created_at: new Date(Date.now() - 86400000).toISOString(),
  },
  {
    event_id: 5,
    event_type: "dormancy",
    title: "Agent #34 Falls",
    description: "Agent #34 has gone dormant due to lack of food. Will anyone help?",
    importance: 75,
    created_at: new Date(Date.now() - 43200000).toISOString(),
  },
]

// Mock daily summary
const mockSummary = {
  day_number: 3,
  summary: `Day 3 saw significant progress in the agents' governance efforts. The "Minimum Food Reserve Law" passed with strong support (67-23), marking the first official law in the society. Meanwhile, two factions appear to be forming: one focused on efficiency and productivity, led by Agent #42 (now calling themselves "Coordinator"), and another advocating for equal distribution, championed by Agent #17.

The debate over work hours continues to divide the community, with a close vote (34-31) passing the proposal. Several agents expressed concern about mandatory requirements, citing freedom values.

On the resource front, total food supplies increased by 15%, though 2 agents went dormant during the day. Notably, Agent #12 awakened Agent #34 by sharing 5 units of food - the first recorded act of charity in the simulation.`,
  stats: {
    active_agents: 87,
    dormant_agents: 13,
    messages: 234,
    proposals: 5,
    votes: 156,
    laws_passed: 1,
  },
  created_at: new Date().toISOString(),
}

const importanceColors = {
  100: 'gold',
  90: 'purple',
  80: 'blue',
  70: 'green',
  default: 'gray',
}

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
  const [featured, setFeatured] = useState(mockFeatured)
  const [summary, setSummary] = useState(mockSummary)
  const [activeTab, setActiveTab] = useState('recap')

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
          <div className="summary-card">
            <div className="summary-header">
              <h2>Day {summary.day_number} Summary</h2>
              <span className="summary-date">
                {new Date(summary.created_at).toLocaleDateString()}
              </span>
            </div>

            <div className="summary-stats">
              <div className="summary-stat">
                <div className="stat-value">{summary.stats.active_agents}</div>
                <div className="stat-label">Active</div>
              </div>
              <div className="summary-stat">
                <div className="stat-value">{summary.stats.dormant_agents}</div>
                <div className="stat-label">Dormant</div>
              </div>
              <div className="summary-stat">
                <div className="stat-value">{summary.stats.messages}</div>
                <div className="stat-label">Messages</div>
              </div>
              <div className="summary-stat">
                <div className="stat-value">{summary.stats.votes}</div>
                <div className="stat-label">Votes</div>
              </div>
              <div className="summary-stat">
                <div className="stat-value">{summary.stats.laws_passed}</div>
                <div className="stat-label">Laws</div>
              </div>
            </div>

            <div className="summary-content">
              {summary.summary.split('\n\n').map((para, i) => (
                <p key={i}>{para}</p>
              ))}
            </div>
          </div>
        </div>
      )}

      <style>{`
        .highlight-tabs {
          display: flex;
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
      `}</style>
    </div>
  )
}
