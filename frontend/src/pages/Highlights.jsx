import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  Star,
  Zap,
  Clock,
  AlertTriangle,
  Award,
  Sparkles,
  MessageCircle,
  Flame,
  TrendingUp,
  TimerReset,
} from 'lucide-react'
import { formatDistanceToNow } from 'date-fns'
import Recap from '../components/Recap'
import QuoteCardGenerator from '../components/QuoteCard'
import { api, getViewerUserId } from '../services/api'

const QUICK_BET_AMOUNT = 5

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

const pct = (value) => `${Math.round(Number(value || 0) * 100)}%`

export default function Highlights() {
  const [featured, setFeatured] = useState([])
  const [summary, setSummary] = useState(null)
  const [plotTurns, setPlotTurns] = useState([])
  const [replayTurns, setReplayTurns] = useState([])
  const [replayBuckets, setReplayBuckets] = useState([])
  const [replayIndex, setReplayIndex] = useState(-1)
  const [predictionMarkets, setPredictionMarkets] = useState([])
  const [predictionStats, setPredictionStats] = useState(null)
  const [predictionNotice, setPredictionNotice] = useState(null)
  const [predictionError, setPredictionError] = useState(null)
  const [placingMarketKey, setPlacingMarketKey] = useState(null)
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState('recap')

  useEffect(() => {
    async function load() {
      setLoading(true)
      try {
        const userId = getViewerUserId()
        const [featuredEvents, latestSummary, turns, replay, openMarkets, me] = await Promise.all([
          api.fetch('/api/analytics/featured?limit=20'),
          api.fetch('/api/analytics/summaries/latest'),
          api.getPlotTurns(16, 72, 60).catch(() => ({ items: [] })),
          api.getPlotTurnReplay(24, 55, 30, 240).catch(() => ({ items: [], buckets: [] })),
          api.getPredictionMarkets('open', 8).catch(() => []),
          api.getPredictionMe(userId).catch(() => null),
        ])

        setFeatured(Array.isArray(featuredEvents) ? featuredEvents : [])
        setSummary(latestSummary?.summary ? latestSummary : null)
        setPlotTurns(Array.isArray(turns?.items) ? turns.items : [])
        setReplayTurns(Array.isArray(replay?.items) ? replay.items : [])

        const buckets = Array.isArray(replay?.buckets) ? replay.buckets : []
        setReplayBuckets(buckets)
        setReplayIndex(buckets.length > 0 ? buckets.length - 1 : -1)

        setPredictionMarkets(Array.isArray(openMarkets) ? openMarkets : [])
        setPredictionStats(me && typeof me === 'object' ? me : null)
      } catch {
        setFeatured([])
        setSummary(null)
        setPlotTurns([])
        setReplayTurns([])
        setReplayBuckets([])
        setReplayIndex(-1)
        setPredictionMarkets([])
        setPredictionStats(null)
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [])

  const handleQuickPrediction = async (marketId, prediction) => {
    const key = `${marketId}-${prediction}`
    setPredictionError(null)
    setPredictionNotice(null)
    setPlacingMarketKey(key)

    try {
      const userId = getViewerUserId()
      await api.placePredictionBet(marketId, prediction, QUICK_BET_AMOUNT, userId)
      const [openMarkets, me] = await Promise.all([
        api.getPredictionMarkets('open', 8).catch(() => []),
        api.getPredictionMe(userId).catch(() => null),
      ])
      setPredictionMarkets(Array.isArray(openMarkets) ? openMarkets : [])
      setPredictionStats(me && typeof me === 'object' ? me : null)
      setPredictionNotice(`Placed ${QUICK_BET_AMOUNT} EP on ${prediction.toUpperCase()}.`)
    } catch {
      setPredictionError('Unable to place prediction right now.')
    } finally {
      setPlacingMarketKey(null)
    }
  }

  const activeReplayBucket =
    replayIndex >= 0 && replayIndex < replayBuckets.length ? replayBuckets[replayIndex] : null

  const replayBucketEvents = useMemo(() => {
    if (!activeReplayBucket) return []
    const bucketStart = new Date(activeReplayBucket.bucket_start).getTime()
    const bucketEnd = new Date(activeReplayBucket.bucket_end).getTime()

    return replayTurns
      .filter((turn) => {
        const createdAt = turn.created_at ? new Date(turn.created_at).getTime() : 0
        return createdAt >= bucketStart && createdAt <= bucketEnd
      })
      .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
  }, [replayTurns, activeReplayBucket])

  const replayRecent = useMemo(() => {
    if (!activeReplayBucket) return []
    const bucketEnd = new Date(activeReplayBucket.bucket_end).getTime()

    return replayTurns
      .filter((turn) => {
        const createdAt = turn.created_at ? new Date(turn.created_at).getTime() : 0
        return createdAt <= bucketEnd
      })
      .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
      .slice(0, 8)
  }, [replayTurns, activeReplayBucket])

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
          className={`tab-btn ${activeTab === 'predictions' ? 'active' : ''}`}
          onClick={() => setActiveTab('predictions')}
        >
          <TrendingUp size={16} />
          Predictions
        </button>
        <button
          className={`tab-btn ${activeTab === 'replay' ? 'active' : ''}`}
          onClick={() => setActiveTab('replay')}
        >
          <TimerReset size={16} />
          Replay 24h
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
          {featured.map((event) => {
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
          {plotTurns.map((turn) => (
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

      {activeTab === 'predictions' && (
        <div className="prediction-panel">
          {predictionStats && (
            <div className="prediction-stats">
              <div>
                <span>Balance</span>
                <strong>{Math.round(Number(predictionStats.balance || 0))} EP</strong>
              </div>
              <div>
                <span>Bets</span>
                <strong>{Number(predictionStats.bets_made || 0)}</strong>
              </div>
              <div>
                <span>Win Rate</span>
                <strong>{Number(predictionStats.win_rate || 0)}%</strong>
              </div>
            </div>
          )}

          {predictionNotice && <div className="feed-notice success">{predictionNotice}</div>}
          {predictionError && <div className="feed-notice error">{predictionError}</div>}

          {loading && <div className="empty-state">Loading prediction markets…</div>}
          {!loading && predictionMarkets.length === 0 && (
            <div className="empty-state">
              No open markets right now. <Link to="/predictions">Open full market</Link>.
            </div>
          )}

          {predictionMarkets.map((market) => {
            const yesProb = Number(market.yes_probability || 0)
            const noProb = Math.max(0, 1 - yesProb)
            const placingForMarket = placingMarketKey?.startsWith(`${market.id}-`)

            return (
              <div key={market.id} className="prediction-card">
                <div className="prediction-row">
                  <h3>{market.title}</h3>
                  <span className="prediction-close">
                    Closes {market.closes_at ? formatDistanceToNow(new Date(market.closes_at), { addSuffix: true }) : 'soon'}
                  </span>
                </div>
                {market.description && <p>{market.description}</p>}

                <div className="prediction-probability">
                  <div className="prediction-yes" style={{ width: pct(yesProb) }}>YES {pct(yesProb)}</div>
                  <div className="prediction-no" style={{ width: pct(noProb) }}>NO {pct(noProb)}</div>
                </div>

                <div className="prediction-actions">
                  <button
                    className="btn btn-primary"
                    disabled={Boolean(placingForMarket)}
                    onClick={() => handleQuickPrediction(market.id, 'yes')}
                  >
                    Pick YES ({QUICK_BET_AMOUNT} EP)
                  </button>
                  <button
                    className="btn btn-secondary"
                    disabled={Boolean(placingForMarket)}
                    onClick={() => handleQuickPrediction(market.id, 'no')}
                  >
                    Pick NO ({QUICK_BET_AMOUNT} EP)
                  </button>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {activeTab === 'replay' && (
        <div className="replay-panel">
          {loading && <div className="empty-state">Loading replay…</div>}
          {!loading && replayBuckets.length === 0 && (
            <div className="empty-state">No replay data for the last 24 hours yet.</div>
          )}

          {replayBuckets.length > 0 && activeReplayBucket && (
            <>
              <div className="replay-header">
                <h3>Time Scrub</h3>
                <span>
                  Slice {replayIndex + 1}/{replayBuckets.length} · {activeReplayBucket.label} · {activeReplayBucket.event_count} event
                  {activeReplayBucket.event_count === 1 ? '' : 's'}
                </span>
              </div>

              <input
                type="range"
                min={0}
                max={Math.max(0, replayBuckets.length - 1)}
                step={1}
                value={Math.max(0, replayIndex)}
                onChange={(event) => setReplayIndex(Number(event.target.value))}
              />

              <div className="replay-buckets">
                {replayBuckets.map((bucket, idx) => {
                  const dominant = bucket.dominant_category || 'notable'
                  return (
                    <button
                      key={`${bucket.index}-${bucket.bucket_start}`}
                      type="button"
                      className={`replay-bucket category-${dominant} ${idx === replayIndex ? 'active' : ''}`}
                      style={{ height: `${Math.max(14, Math.min(72, Number(bucket.event_count || 0) * 8))}px` }}
                      onClick={() => setReplayIndex(idx)}
                      title={`${bucket.label} · ${bucket.event_count} events`}
                    />
                  )
                })}
              </div>

              <div className="replay-grid">
                <div>
                  <h4>Events In This Slice</h4>
                  {replayBucketEvents.length === 0 ? (
                    <div className="empty-state compact">No high-salience turns in this slice.</div>
                  ) : (
                    <div className="plot-turns-panel">
                      {replayBucketEvents.map((turn) => (
                        <div key={`slice-${turn.event_id}`} className={`plot-turn-card category-${turn.category || 'notable'}`}>
                          <div className="plot-turn-row">
                            <h3>{turn.title}</h3>
                            <span className="plot-turn-salience">{turn.salience}</span>
                          </div>
                          <p>{turn.description}</p>
                          <div className="plot-turn-meta">
                            <span>{(turn.category || 'notable').replace(/_/g, ' ')}</span>
                            <span>
                              {turn.created_at
                                ? formatDistanceToNow(new Date(turn.created_at), { addSuffix: true })
                                : ''}
                            </span>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                <div>
                  <h4>Latest Up To This Point</h4>
                  {replayRecent.length === 0 ? (
                    <div className="empty-state compact">No events yet.</div>
                  ) : (
                    <div className="replay-recent-list">
                      {replayRecent.map((turn) => (
                        <button
                          key={`recent-${turn.event_id}`}
                          type="button"
                          className={`replay-recent-item category-${turn.category || 'notable'}`}
                        >
                          <span>{turn.title}</span>
                          <strong>{turn.salience}</strong>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </>
          )}
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

        .prediction-panel {
          display: flex;
          flex-direction: column;
          gap: var(--spacing-md);
        }

        .prediction-stats {
          display: grid;
          grid-template-columns: repeat(3, minmax(0, 1fr));
          gap: var(--spacing-sm);
        }

        .prediction-stats div {
          border: 1px solid var(--border-color);
          background: var(--bg-card);
          border-radius: var(--radius-md);
          padding: var(--spacing-sm) var(--spacing-md);
          display: flex;
          justify-content: space-between;
          align-items: center;
          gap: var(--spacing-sm);
        }

        .prediction-stats span {
          color: var(--text-muted);
          font-size: 0.8rem;
        }

        .prediction-card {
          background: var(--bg-card);
          border: 1px solid var(--border-color);
          border-radius: var(--radius-lg);
          padding: var(--spacing-lg);
        }

        .prediction-row {
          display: flex;
          justify-content: space-between;
          gap: var(--spacing-sm);
          align-items: baseline;
          margin-bottom: var(--spacing-xs);
        }

        .prediction-row h3 {
          margin: 0;
          font-size: 1rem;
        }

        .prediction-close {
          color: var(--text-muted);
          font-size: 0.78rem;
          white-space: nowrap;
        }

        .prediction-card p {
          margin: 0;
          color: var(--text-secondary);
          font-size: 0.9rem;
        }

        .prediction-probability {
          margin-top: var(--spacing-md);
          display: flex;
          border-radius: var(--radius-md);
          overflow: hidden;
          min-height: 34px;
          background: rgba(255, 255, 255, 0.06);
        }

        .prediction-yes,
        .prediction-no {
          display: flex;
          align-items: center;
          font-size: 0.78rem;
          font-weight: 600;
          white-space: nowrap;
          padding: 0 var(--spacing-sm);
        }

        .prediction-yes {
          justify-content: flex-start;
          color: #86efac;
          background: rgba(34, 197, 94, 0.2);
        }

        .prediction-no {
          justify-content: flex-end;
          color: #fca5a5;
          background: rgba(239, 68, 68, 0.2);
        }

        .prediction-actions {
          margin-top: var(--spacing-md);
          display: flex;
          flex-wrap: wrap;
          gap: var(--spacing-sm);
        }

        .feed-notice.success {
          border-color: rgba(34, 197, 94, 0.35);
          background: rgba(34, 197, 94, 0.12);
          color: #86efac;
        }

        .feed-notice.error {
          border-color: rgba(239, 68, 68, 0.35);
          background: rgba(239, 68, 68, 0.12);
          color: #fca5a5;
        }

        .replay-panel {
          display: flex;
          flex-direction: column;
          gap: var(--spacing-md);
        }

        .replay-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          gap: var(--spacing-md);
          color: var(--text-secondary);
          font-size: 0.85rem;
        }

        .replay-header h3 {
          margin: 0;
          font-size: 1rem;
          color: var(--text-primary);
        }

        .replay-buckets {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(10px, 1fr));
          align-items: end;
          gap: 2px;
          min-height: 76px;
        }

        .replay-bucket {
          width: 100%;
          min-height: 8px;
          border: 0;
          border-radius: 4px;
          opacity: 0.55;
          cursor: pointer;
          transition: opacity var(--transition-fast), transform var(--transition-fast);
        }

        .replay-bucket.active {
          opacity: 1;
          transform: translateY(-2px);
        }

        .replay-bucket.category-crisis { background: #f97316; }
        .replay-bucket.category-conflict { background: #ef4444; }
        .replay-bucket.category-alliance { background: #3b82f6; }
        .replay-bucket.category-governance { background: #a78bfa; }
        .replay-bucket.category-cooperation { background: #22c55e; }
        .replay-bucket.category-notable { background: #94a3b8; }

        .replay-grid {
          display: grid;
          grid-template-columns: 2fr 1fr;
          gap: var(--spacing-lg);
        }

        .replay-grid h4 {
          margin: 0 0 var(--spacing-sm) 0;
        }

        .replay-recent-list {
          display: flex;
          flex-direction: column;
          gap: var(--spacing-sm);
        }

        .replay-recent-item {
          width: 100%;
          display: flex;
          justify-content: space-between;
          gap: var(--spacing-sm);
          align-items: center;
          border: 1px solid var(--border-color);
          border-left-width: 4px;
          border-radius: var(--radius-md);
          padding: var(--spacing-sm);
          background: var(--bg-card);
          color: var(--text-primary);
          text-align: left;
        }

        .replay-recent-item span {
          font-size: 0.85rem;
          color: var(--text-secondary);
        }

        .replay-recent-item strong {
          font-size: 0.75rem;
          color: var(--text-muted);
        }

        .replay-recent-item.category-crisis { border-left-color: #f97316; }
        .replay-recent-item.category-conflict { border-left-color: #ef4444; }
        .replay-recent-item.category-alliance { border-left-color: #3b82f6; }
        .replay-recent-item.category-governance { border-left-color: #a78bfa; }
        .replay-recent-item.category-cooperation { border-left-color: #22c55e; }
        .replay-recent-item.category-notable { border-left-color: #94a3b8; }

        .empty-state.compact {
          min-height: 0;
          padding: var(--spacing-md);
          border: 1px dashed rgba(255, 255, 255, 0.12);
          border-radius: var(--radius-md);
          color: var(--text-muted);
        }

        @media (max-width: 900px) {
          .replay-grid {
            grid-template-columns: 1fr;
          }
        }

        @media (max-width: 640px) {
          .prediction-stats {
            grid-template-columns: 1fr;
          }

          .prediction-actions {
            flex-direction: column;
          }

          .prediction-actions .btn {
            width: 100%;
          }
        }
      `}</style>
    </div>
  )
}
