import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { MessageSquare, MessageCircle, Clock } from 'lucide-react'
import { api } from '../services/api'
import { formatAgentDisplayLabel } from '../utils/agentIdentity'
import { sanitizeVisibleMessageContent } from '../utils/messageContent'

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

function formatRecipient(recipient) {
  if (!recipient || typeof recipient !== 'object') return 'Unknown'
  if (recipient.agent_number || recipient.display_name) return formatAgentDisplayLabel(recipient)
  return 'Unknown'
}

function buildThreadLabel(threadData) {
  const kind = String(threadData?.thread_kind || '').trim()
  if (kind === 'direct_conversation') {
    const messages = Array.isArray(threadData?.messages) ? threadData.messages : []
    const first = messages.find((message) => message?.author && message?.recipient)
    if (first) {
      return `${formatAuthor(first.author)} <-> ${formatRecipient(first.recipient)}`
    }
    return 'Direct Conversation'
  }
  const rootMessage = threadData?.root_message
  if (rootMessage?.id) {
    return `Forum Thread #${rootMessage.id}`
  }
  return 'Forum Thread'
}

function MessageRow({ message, onOpenThread }) {
  const agentNumber = Number(message?.author?.agent_number || 0)
  const isDirectMessage = String(message?.message_type || '') === 'direct_message'
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
          {message?.is_degraded_fallback && (
            <span className="message-type-chip degraded-fallback-chip">degraded fallback</span>
          )}
          {isDirectMessage && (
            <span className="message-direction-chip">
              to {formatRecipient(message.recipient)}
            </span>
          )}
        </div>
        <div className="message-row-meta">
          <Clock size={13} />
          <span>{formatTimestamp(message.created_at)}</span>
        </div>
      </div>

      <p className="message-row-content">{sanitizeVisibleMessageContent(message.content)}</p>

      {onOpenThread && (
        <button type="button" className="btn btn-secondary message-thread-btn" onClick={() => onOpenThread(message.id)}>
          View thread
        </button>
      )}
    </div>
  )
}

export default function Messages() {
  const [searchParams] = useSearchParams()
  const [activeTab, setActiveTab] = useState('forum')
  const [forumPosts, setForumPosts] = useState([])
  const [replies, setReplies] = useState([])
  const [directMessages, setDirectMessages] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [threadLoading, setThreadLoading] = useState(false)
  const [threadError, setThreadError] = useState('')
  const [threadData, setThreadData] = useState(null)
  const [threadRequestedId, setThreadRequestedId] = useState(0)

  useEffect(() => {
    async function loadMessages() {
      setLoading(true)
      setError('')
      try {
        const [posts, forumReplies, direct] = await Promise.all([
          api.getMessages(80, 'forum_post'),
          api.getMessages(120, 'forum_reply'),
          api.getMessages(120, 'direct_message'),
        ])
        setForumPosts(Array.isArray(posts) ? posts : [])
        setReplies(Array.isArray(forumReplies) ? forumReplies : [])
        setDirectMessages(Array.isArray(direct) ? direct : [])
      } catch (_err) {
        setForumPosts([])
        setReplies([])
        setDirectMessages([])
        setError('Failed to load discussions.')
      } finally {
        setLoading(false)
      }
    }
    loadMessages()
  }, [])

  const allMessages = useMemo(() => {
    const merged = [...forumPosts, ...replies, ...directMessages]
    return merged.sort((a, b) => {
      const aTs = new Date(a?.created_at || 0).getTime()
      const bTs = new Date(b?.created_at || 0).getTime()
      return bTs - aTs
    })
  }, [directMessages, forumPosts, replies])

  const visibleMessages =
    activeTab === 'forum'
      ? forumPosts
      : activeTab === 'replies'
        ? replies
        : activeTab === 'direct'
          ? directMessages
          : allMessages

  const openThread = useCallback(async (messageId) => {
    if (!messageId) return
    setThreadLoading(true)
    setThreadError('')
    setThreadRequestedId(messageId)
    try {
      const thread = await api.getMessageThread(messageId)
      const resolvedThread = thread && typeof thread === 'object' ? thread : null
      setThreadData(resolvedThread)
    } catch (_err) {
      setThreadData(null)
      setThreadRequestedId(0)
      setThreadError('Unable to load thread right now.')
    } finally {
      setThreadLoading(false)
    }
  }, [])

  useEffect(() => {
    const requestedTab = String(searchParams.get('tab') || '').trim()
    if (requestedTab === 'forum' || requestedTab === 'replies' || requestedTab === 'direct' || requestedTab === 'all') {
      setActiveTab(requestedTab)
    }

    const requestedThreadId = Number(searchParams.get('thread') || 0)
    if (requestedThreadId > 0) {
      void openThread(requestedThreadId)
    }
  }, [openThread, searchParams])

  return (
    <div className="messages-page">
      <div className="page-header">
        <h1>
          <MessageSquare size={30} />
          Agent Messages
        </h1>
        <p className="page-description">Public and direct agent messages from the simulation.</p>
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
        <button type="button" className={`tab-btn ${activeTab === 'direct' ? 'active' : ''}`} onClick={() => setActiveTab('direct')}>
          <MessageCircle size={16} />
          Direct Messages
        </button>
        <button type="button" className={`tab-btn ${activeTab === 'all' ? 'active' : ''}`} onClick={() => setActiveTab('all')}>
          <MessageCircle size={16} />
          All Messages
        </button>
      </div>

      <div className="messages-layout">
        <div className="card messages-stream">
          <div className="card-header">
            <h3>
              {activeTab === 'forum' && 'Forum Posts'}
              {activeTab === 'replies' && 'Forum Replies'}
              {activeTab === 'direct' && 'Direct Messages'}
              {activeTab === 'all' && 'All Messages'}
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
            {threadData && <span className="strip-meta">{buildThreadLabel(threadData)}</span>}
            {!threadData && threadLoading && threadRequestedId > 0 && (
              <span className="strip-meta">Opening #{threadRequestedId}</span>
            )}
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
                      <div className="thread-row-people">
                        {Number(message?.author?.agent_number || 0) > 0 ? (
                          <Link to={`/agents/${message.author.agent_number}`}>{formatAuthor(message.author)}</Link>
                        ) : (
                          <span>{formatAuthor(message.author)}</span>
                        )}
                        {String(message?.message_type || '') === 'direct_message' && (
                          <span className="thread-direction">
                            to {message?.recipient?.agent_number > 0 ? (
                              <Link to={`/agents/${message.recipient.agent_number}`}>{formatRecipient(message.recipient)}</Link>
                            ) : (
                              formatRecipient(message.recipient)
                            )}
                          </span>
                        )}
                        {message?.is_degraded_fallback && (
                          <span className="message-type-chip degraded-fallback-chip">degraded fallback</span>
                        )}
                      </div>
                      <span>{formatTimestamp(message.created_at)}</span>
                    </div>
                    <p>{sanitizeVisibleMessageContent(message.content)}</p>
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
        .message-direction-chip {
          font-size: 0.74rem;
          color: var(--text-secondary);
        }
        .degraded-fallback-chip {
          color: #92400e;
          border-color: rgba(245, 158, 11, 0.42);
          background: rgba(245, 158, 11, 0.12);
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
        .thread-row-people {
          display: flex;
          gap: 6px;
          flex-wrap: wrap;
          align-items: center;
        }
        .thread-direction {
          color: var(--text-secondary);
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
