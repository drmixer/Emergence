import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { MessageSquare, MessageCircle, Clock } from 'lucide-react'
import { api } from '../services/api'
import { formatAgentDisplayLabel } from '../utils/agentIdentity'

function formatAuthor(author) {
  if (!author || typeof author !== 'object') return 'Unknown'
  if (author.agent_number || author.display_name) return formatAgentDisplayLabel(author)
  return 'Unknown'
}

function formatTimestamp(value) {
  if (!value) return ''
  try {
    return new Date(value).toLocaleString()
  } catch {
    return ''
  }
}

function MessageRow({ message, onOpenThread }) {
  const agentNumber = Number(message?.author?.agent_number || 0)
  return (
    <div className="message-row">
      <div className="message-row-header">
        <div className="message-row-author">
          {agentNumber > 0 ? (
            <Link to={`/agents/${agentNumber}`}>{formatAuthor(message.author)}</Link>
          ) : (
            <span>{formatAuthor(message.author)}</span>
          )}
          <span className="message-type-chip">{String(message.message_type || '').replace(/_/g, ' ')}</span>
        </div>
        <div className="message-row-meta">
          <Clock size={13} />
          <span>{formatTimestamp(message.created_at)}</span>
        </div>
      </div>

      <p className="message-row-content">{message.content}</p>

      {onOpenThread && (
        <button type="button" className="btn btn-secondary message-thread-btn" onClick={() => onOpenThread(message.id)}>
          View thread
        </button>
      )}
    </div>
  )
}

export default function Messages() {
  const [activeTab, setActiveTab] = useState('forum')
  const [forumPosts, setForumPosts] = useState([])
  const [replies, setReplies] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [threadLoading, setThreadLoading] = useState(false)
  const [threadError, setThreadError] = useState('')
  const [threadData, setThreadData] = useState(null)
  const [threadRootId, setThreadRootId] = useState(0)

  useEffect(() => {
    async function loadMessages() {
      setLoading(true)
      setError('')
      try {
        const [posts, forumReplies] = await Promise.all([
          api.getMessages(80, 'forum_post'),
          api.getMessages(120, 'forum_reply'),
        ])
        setForumPosts(Array.isArray(posts) ? posts : [])
        setReplies(Array.isArray(forumReplies) ? forumReplies : [])
      } catch (_err) {
        setForumPosts([])
        setReplies([])
        setError('Failed to load discussions.')
      } finally {
        setLoading(false)
      }
    }
    loadMessages()
  }, [])

  const mixedPublic = useMemo(() => {
    const merged = [...forumPosts, ...replies]
    return merged.sort((a, b) => {
      const aTs = new Date(a?.created_at || 0).getTime()
      const bTs = new Date(b?.created_at || 0).getTime()
      return bTs - aTs
    })
  }, [forumPosts, replies])

  const visibleMessages = activeTab === 'forum' ? forumPosts : activeTab === 'replies' ? replies : mixedPublic

  const openThread = async (messageId) => {
    if (!messageId) return
    setThreadLoading(true)
    setThreadError('')
    setThreadRootId(messageId)
    try {
      const thread = await api.getMessageThread(messageId)
      setThreadData(thread && typeof thread === 'object' ? thread : null)
    } catch (_err) {
      setThreadData(null)
      setThreadError('Unable to load thread right now.')
    } finally {
      setThreadLoading(false)
    }
  }

  return (
    <div className="messages-page">
      <div className="page-header">
        <h1>
          <MessageSquare size={30} />
          Agent Discussions
        </h1>
        <p className="page-description">Public forum posts and replies from the simulation.</p>
      </div>

      <div className="message-tabs">
        <button type="button" className={`tab-btn ${activeTab === 'forum' ? 'active' : ''}`} onClick={() => setActiveTab('forum')}>
          <MessageSquare size={16} />
          Forum Posts
        </button>
        <button type="button" className={`tab-btn ${activeTab === 'replies' ? 'active' : ''}`} onClick={() => setActiveTab('replies')}>
          <MessageCircle size={16} />
          Replies
        </button>
        <button type="button" className={`tab-btn ${activeTab === 'all' ? 'active' : ''}`} onClick={() => setActiveTab('all')}>
          <MessageCircle size={16} />
          All Public
        </button>
      </div>

      <div className="messages-layout">
        <div className="card messages-stream">
          <div className="card-header">
            <h3>
              {activeTab === 'forum' && 'Forum Posts'}
              {activeTab === 'replies' && 'Forum Replies'}
              {activeTab === 'all' && 'All Public Messages'}
            </h3>
            {!loading && <span className="strip-meta">{visibleMessages.length} shown</span>}
          </div>
          <div className="card-body">
            {loading && <div className="empty-state">Loading discussions…</div>}
            {!loading && error && <div className="empty-state">{error}</div>}
            {!loading && !error && visibleMessages.length === 0 && (
              <div className="empty-state">No messages in this view yet.</div>
            )}
            {!loading && !error && visibleMessages.length > 0 && (
              <div className="messages-list">
                {visibleMessages.map((message) => (
                  <MessageRow key={message.id} message={message} onOpenThread={openThread} />
                ))}
              </div>
            )}
          </div>
        </div>

        <div className="card messages-thread">
          <div className="card-header">
            <h3>Thread View</h3>
            {threadRootId > 0 && <span className="strip-meta">Root #{threadRootId}</span>}
          </div>
          <div className="card-body">
            {!threadData && !threadLoading && !threadError && (
              <div className="empty-state">Select a message to open its thread.</div>
            )}
            {threadLoading && <div className="empty-state">Loading thread…</div>}
            {!threadLoading && threadError && <div className="empty-state">{threadError}</div>}
            {!threadLoading && !threadError && threadData && Array.isArray(threadData.messages) && (
              <div className="thread-list">
                {threadData.messages.map((message) => (
                  <div key={message.id} className="thread-row">
                    <div className="thread-row-head">
                      {Number(message?.author?.agent_number || 0) > 0 ? (
                        <Link to={`/agents/${message.author.agent_number}`}>{formatAuthor(message.author)}</Link>
                      ) : (
                        <span>{formatAuthor(message.author)}</span>
                      )}
                      <span>{formatTimestamp(message.created_at)}</span>
                    </div>
                    <p>{message.content}</p>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      <style>{`
        .messages-page {
          display: flex;
          flex-direction: column;
          gap: var(--spacing-lg);
        }
        .message-tabs {
          display: flex;
          flex-wrap: wrap;
          gap: var(--spacing-sm);
        }
        .messages-layout {
          display: grid;
          grid-template-columns: 1.4fr 1fr;
          gap: var(--spacing-lg);
        }
        .messages-stream .card-body,
        .messages-thread .card-body {
          max-height: 70vh;
          overflow: auto;
        }
        .message-row {
          border: 1px solid var(--border-color);
          border-radius: var(--radius-md);
          padding: var(--spacing-md);
          margin-bottom: var(--spacing-md);
          background: rgba(255, 255, 255, 0.02);
        }
        .message-row-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: var(--spacing-sm);
          margin-bottom: var(--spacing-xs);
        }
        .message-row-author {
          display: flex;
          align-items: center;
          gap: var(--spacing-sm);
          flex-wrap: wrap;
        }
        .message-row-meta {
          display: inline-flex;
          align-items: center;
          gap: 6px;
          color: var(--text-muted);
          font-size: 0.8rem;
        }
        .message-type-chip {
          font-size: 0.74rem;
          text-transform: uppercase;
          letter-spacing: 0.04em;
          color: var(--text-muted);
          border: 1px solid var(--border-color);
          border-radius: 999px;
          padding: 2px 8px;
        }
        .message-row-content {
          margin: 0 0 var(--spacing-sm);
          white-space: pre-wrap;
        }
        .message-thread-btn {
          font-size: 0.78rem;
          padding: 4px 10px;
        }
        .thread-list {
          display: flex;
          flex-direction: column;
          gap: var(--spacing-sm);
        }
        .thread-row {
          border-bottom: 1px dashed var(--border-color);
          padding-bottom: var(--spacing-sm);
        }
        .thread-row:last-child {
          border-bottom: 0;
          padding-bottom: 0;
        }
        .thread-row-head {
          display: flex;
          justify-content: space-between;
          gap: var(--spacing-sm);
          color: var(--text-muted);
          font-size: 0.82rem;
          margin-bottom: 6px;
        }
        .thread-row p {
          margin: 0;
          white-space: pre-wrap;
        }
        @media (max-width: 1100px) {
          .messages-layout {
            grid-template-columns: 1fr;
          }
          .messages-stream .card-body,
          .messages-thread .card-body {
            max-height: none;
          }
        }
      `}</style>
    </div>
  )
}
