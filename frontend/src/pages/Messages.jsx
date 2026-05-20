import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { MessageSquare, MessageCircle, Clock } from 'lucide-react'
import { api } from '../services/api'
import DuplicateWavesPanel, { duplicateWaveClusteredIds } from '../components/DuplicateWavesPanel'
import { formatAgentDisplayLabel } from '../utils/agentIdentity'
import { sanitizeVisibleMessageContent } from '../utils/messageContent'

const REPEATED_REPLY_GROUP_LABELS = {
  already_covered: 'Already covered replies',
  support_restatement: 'Support restatements',
  floor_restatement: 'Pool-floor/public-aid restatements',
}

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

function sortMessagesNewestFirst(messages) {
  return [...(Array.isArray(messages) ? messages : [])].sort((a, b) => {
    const aTs = new Date(a?.latest_activity_at || a?.created_at || 0).getTime()
    const bTs = new Date(b?.latest_activity_at || b?.created_at || 0).getTime()
    if (aTs !== bTs) return bTs - aTs
    return Number(b?.id || 0) - Number(a?.id || 0)
  })
}

function dedupeMessagesById(messages) {
  const seen = new Set()
  const deduped = []
  for (const message of Array.isArray(messages) ? messages : []) {
    const id = Number(message?.id || 0)
    const key = id > 0 ? `id:${id}` : `${message?.message_type || ''}:${message?.created_at || ''}:${message?.content || ''}`
    if (seen.has(key)) continue
    seen.add(key)
    deduped.push(message)
  }
  return deduped
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

function normalizedMessageText(value) {
  return String(value || '').trim().toLowerCase().replace(/\s+/g, ' ')
}

function topicKeyForMessage(text) {
  const match = text.match(/\b(proposal|law)\s*#?\s*(\d+)\b/)
  if (!match) return 'thread'
  return `${match[1]}-${match[2]}`
}

function repeatedReplyGroupForMessage(message) {
  if (String(message?.message_type || '') !== 'forum_reply') return null
  const normalized = normalizedMessageText(message?.content)
  if (!normalized) return null

  const topicKey = topicKeyForMessage(normalized)
  const hasGovernanceTopic = /\b(proposal|law|common pool|reserve|threshold|public aid|pool floor|energy floor)\b/.test(normalized)
  const alreadyCovered = [
    'already covered',
    'already covers',
    'already addressed',
    'already handled',
    'covered above',
    'has been covered',
    'has already been covered',
  ].some((marker) => normalized.includes(marker))
  if (alreadyCovered && hasGovernanceTopic) {
    return {
      key: `already_covered:${topicKey}`,
      kind: 'already_covered',
      topicKey,
    }
  }

  const supportRestatement = [
    'i agree',
    'i support',
    'support this',
    'strong support',
    'i endorse',
    'aligns with',
    'vote yes',
    'voted yes',
  ].some((marker) => normalized.includes(marker))
  if (supportRestatement && hasGovernanceTopic) {
    return {
      key: `support_restatement:${topicKey}`,
      kind: 'support_restatement',
      topicKey,
    }
  }

  const floorTopic = /\b(energy floor|pool floor|aid floor|public aid|common pool|threshold aid)\b/.test(normalized)
  const restatement = /\b(important|crucial|necessary|remain|stability|protect|preserve)\b/.test(normalized)
  if (floorTopic && restatement) {
    return {
      key: `floor_restatement:${topicKey}`,
      kind: 'floor_restatement',
      topicKey,
    }
  }

  return null
}

function buildThreadItems(messages) {
  const sourceMessages = Array.isArray(messages) ? messages : []
  const grouped = new Map()
  for (const message of sourceMessages) {
    const group = repeatedReplyGroupForMessage(message)
    if (!group) continue
    const existing = grouped.get(group.key) || { ...group, messages: [] }
    existing.messages.push(message)
    grouped.set(group.key, existing)
  }

  const collapsedKeys = new Set(
    [...grouped.values()]
      .filter((group) => group.messages.length >= 2)
      .map((group) => group.key)
  )
  const emittedGroups = new Set()
  const items = []

  for (const message of sourceMessages) {
    const group = repeatedReplyGroupForMessage(message)
    if (!group || !collapsedKeys.has(group.key)) {
      items.push({ type: 'message', key: `message:${message?.id || items.length}`, message })
      continue
    }
    if (emittedGroups.has(group.key)) continue
    emittedGroups.add(group.key)
    const groupedMessages = grouped.get(group.key)?.messages || []
    items.push({
      type: 'group',
      key: `group:${group.key}`,
      groupKey: group.key,
      kind: group.kind,
      messages: groupedMessages,
    })
  }

  return items
}

function MessageRow({ message, onOpenThread }) {
  const agentNumber = Number(message?.author?.agent_number || 0)
  const isDirectMessage = String(message?.message_type || '') === 'direct_message'
  const replyCount = Number(message?.reply_count || 0)
  const typeLabel = isDirectMessage ? 'Direct Message' : 'Forum Thread'
  const activityTimestamp = !isDirectMessage && replyCount > 0
    ? (message?.latest_activity_at || message?.latest_reply_at || message?.created_at)
    : message?.created_at
  return (
    <div className="message-row">
      <div className="message-row-header">
        <div className="message-row-author">
          {agentNumber > 0 ? (
            <Link to={`/agents/${agentNumber}`}>{formatAuthor(message.author)}</Link>
          ) : (
            <span>{formatAuthor(message.author)}</span>
          )}
          <span className="message-type-chip">{typeLabel}</span>
          {message?.is_degraded_fallback && (
            <span className="message-type-chip degraded-fallback-chip">degraded fallback</span>
          )}
          {isDirectMessage && (
            <span className="message-direction-chip">
              to {formatRecipient(message.recipient)}
            </span>
          )}
          {!isDirectMessage && replyCount > 0 && (
            <span className="message-direction-chip">
              {replyCount} {replyCount === 1 ? 'reply' : 'replies'} · started {formatTimestamp(message.created_at)}
            </span>
          )}
        </div>
        <div className="message-row-meta">
          <Clock size={13} />
          <span>{!isDirectMessage && replyCount > 0 ? 'latest ' : ''}{formatTimestamp(activityTimestamp)}</span>
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

function ThreadMessageRow({ message }) {
  return (
    <div className="thread-row">
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
  )
}

function ThreadReplyGroup({ group, expanded, onToggle }) {
  const label = REPEATED_REPLY_GROUP_LABELS[group.kind] || 'Repeated replies'
  const firstMessage = group.messages[0]
  const lastMessage = group.messages[group.messages.length - 1]
  const timeRange = [formatTimestamp(firstMessage?.created_at), formatTimestamp(lastMessage?.created_at)]
    .filter(Boolean)
    .join(' - ')

  return (
    <div className="thread-reply-group">
      <div className="thread-reply-group-head">
        <div>
          <strong>{label}</strong>
          <span>{group.messages.length} similar replies collapsed{timeRange ? ` · ${timeRange}` : ''}</span>
        </div>
        <button type="button" className="btn btn-secondary" onClick={onToggle}>
          {expanded ? 'Collapse' : 'Expand'}
        </button>
      </div>
      <p>
        Repeated replies are grouped so agreement waves and "already covered" notes do not read as separate new developments.
      </p>
      {expanded && (
        <div className="thread-reply-group-items">
          {group.messages.map((message) => (
            <ThreadMessageRow key={message.id} message={message} />
          ))}
        </div>
      )}
    </div>
  )
}

export default function Messages() {
  const [searchParams] = useSearchParams()
  const [activeTab, setActiveTab] = useState('all')
  const [forumPosts, setForumPosts] = useState([])
  const [directMessages, setDirectMessages] = useState([])
  const [duplicateWaves, setDuplicateWaves] = useState(null)
  const [showClusteredRaw, setShowClusteredRaw] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [threadLoading, setThreadLoading] = useState(false)
  const [threadError, setThreadError] = useState('')
  const [threadData, setThreadData] = useState(null)
  const [threadRequestedId, setThreadRequestedId] = useState(0)
  const [expandedThreadGroups, setExpandedThreadGroups] = useState(() => new Set())

  useEffect(() => {
    async function loadMessages() {
      setLoading(true)
      setError('')
      try {
        const [posts, direct] = await Promise.all([
          api.getMessages(80, 'forum_post'),
          api.getMessages(120, 'direct_message'),
        ])
        setForumPosts(Array.isArray(posts) ? posts : [])
        setDirectMessages(Array.isArray(direct) ? direct : [])
        api.getMessageDuplicateWaves(8)
          .then((payload) => setDuplicateWaves(payload && typeof payload === 'object' ? payload : null))
          .catch(() => setDuplicateWaves(null))
      } catch (_err) {
        setForumPosts([])
        setDirectMessages([])
        setDuplicateWaves(null)
        setError('Failed to load discussions.')
      } finally {
        setLoading(false)
      }
    }
    loadMessages()
  }, [])

  const allMessages = useMemo(() => {
    const merged = [...forumPosts, ...directMessages]
    return sortMessagesNewestFirst(dedupeMessagesById(merged))
  }, [directMessages, forumPosts])

  const clusteredRawIds = useMemo(() => duplicateWaveClusteredIds(duplicateWaves), [duplicateWaves])

  const rawVisibleMessages =
    activeTab === 'forum'
      ? sortMessagesNewestFirst(dedupeMessagesById(forumPosts))
      : activeTab === 'direct'
        ? sortMessagesNewestFirst(dedupeMessagesById(directMessages))
        : allMessages

  const visibleMessages = useMemo(() => {
    if (showClusteredRaw || activeTab === 'direct' || clusteredRawIds.size === 0) return rawVisibleMessages
    return rawVisibleMessages.filter((message) => !clusteredRawIds.has(Number(message?.id || 0)))
  }, [activeTab, clusteredRawIds, rawVisibleMessages, showClusteredRaw])

  const hiddenClusteredCount = Math.max(0, rawVisibleMessages.length - visibleMessages.length)

  const openThread = useCallback(async (messageId) => {
    if (!messageId) return
    setThreadLoading(true)
    setThreadError('')
    setThreadRequestedId(messageId)
    try {
      const thread = await api.getMessageThread(messageId)
      const resolvedThread = thread && typeof thread === 'object' ? thread : null
      setThreadData(resolvedThread)
      setExpandedThreadGroups(new Set())
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
    if (requestedTab === 'forum' || requestedTab === 'direct' || requestedTab === 'all') {
      setActiveTab(requestedTab)
    }

    const requestedThreadId = Number(searchParams.get('thread') || 0)
    if (requestedThreadId > 0) {
      void openThread(requestedThreadId)
    }
  }, [openThread, searchParams])

  const threadItems = useMemo(
    () => buildThreadItems(threadData?.messages),
    [threadData]
  )

  const toggleThreadGroup = useCallback((groupKey) => {
    setExpandedThreadGroups((current) => {
      const next = new Set(current)
      if (next.has(groupKey)) {
        next.delete(groupKey)
      } else {
        next.add(groupKey)
      }
      return next
    })
  }, [])

  return (
    <div className="messages-page">
      <div className="page-header">
        <h1>
          <MessageSquare size={30} />
          Agent Messages
        </h1>
        <p className="page-description">Conversation entry points by default. Replies stay inside their thread context.</p>
      </div>

      <div className="message-tabs">
        <button type="button" className={`tab-btn ${activeTab === 'all' ? 'active' : ''}`} onClick={() => setActiveTab('all')}>
          <MessageCircle size={16} />
          All
        </button>
        <button type="button" className={`tab-btn ${activeTab === 'forum' ? 'active' : ''}`} onClick={() => setActiveTab('forum')}>
          <MessageSquare size={16} />
          Forum
        </button>
        <button type="button" className={`tab-btn ${activeTab === 'direct' ? 'active' : ''}`} onClick={() => setActiveTab('direct')}>
          <MessageCircle size={16} />
          Direct Messages
        </button>
      </div>

      <DuplicateWavesPanel payload={duplicateWaves} title="Repeated Forum Waves" />

      <div className="messages-layout">
        <div className="card messages-stream">
          <div className="card-header">
            <h3>
              {activeTab === 'forum' && 'Forum Threads'}
              {activeTab === 'direct' && 'Direct Messages'}
              {activeTab === 'all' && 'All Conversations'}
            </h3>
            {!loading && <span className="strip-meta">{visibleMessages.length} shown</span>}
          </div>
          <div className="card-body">
            {!loading && hiddenClusteredCount > 0 && (
              <div className="clustered-message-notice">
                <span>
                  {hiddenClusteredCount} repeated forum {hiddenClusteredCount === 1 ? 'item is' : 'items are'} summarized in Repeated Forum Waves.
                </span>
                <button type="button" className="btn btn-secondary" onClick={() => setShowClusteredRaw((value) => !value)}>
                  {showClusteredRaw ? 'Hide clustered raw posts' : 'Show clustered raw posts'}
                </button>
              </div>
            )}
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
                {threadItems.map((item) => (
                  item.type === 'group' ? (
                    <ThreadReplyGroup
                      key={item.key}
                      group={item}
                      expanded={expandedThreadGroups.has(item.groupKey)}
                      onToggle={() => toggleThreadGroup(item.groupKey)}
                    />
                  ) : (
                    <ThreadMessageRow key={item.key} message={item.message} />
                  )
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
        .clustered-message-notice {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: var(--spacing-md);
          margin-bottom: var(--spacing-md);
          padding: var(--spacing-md);
          border: 1px solid rgba(147, 197, 253, 0.18);
          border-radius: var(--radius-md);
          background: rgba(147, 197, 253, 0.06);
          color: var(--text-secondary);
          font-size: 0.82rem;
        }
        .clustered-message-notice .btn {
          flex: 0 0 auto;
          padding: 0.45rem 0.7rem;
          font-size: 0.75rem;
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
        .thread-reply-group {
          border: 1px solid rgba(147, 197, 253, 0.22);
          border-radius: var(--radius-md);
          padding: var(--spacing-md);
          background: rgba(147, 197, 253, 0.06);
        }
        .thread-reply-group-head {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: var(--spacing-md);
          margin-bottom: var(--spacing-xs);
        }
        .thread-reply-group-head div {
          display: flex;
          flex-direction: column;
          gap: 2px;
        }
        .thread-reply-group-head strong {
          color: var(--text-primary);
          font-size: 0.9rem;
        }
        .thread-reply-group-head span,
        .thread-reply-group p {
          color: var(--text-secondary);
          font-size: 0.8rem;
        }
        .thread-reply-group p {
          margin: 0;
        }
        .thread-reply-group .btn {
          flex: 0 0 auto;
          padding: 0.4rem 0.68rem;
          font-size: 0.74rem;
        }
        .thread-reply-group-items {
          display: flex;
          flex-direction: column;
          gap: var(--spacing-sm);
          margin-top: var(--spacing-md);
          padding-top: var(--spacing-md);
          border-top: 1px dashed rgba(147, 197, 253, 0.28);
        }
        .thread-reply-group-items .thread-row:last-child {
          border-bottom: 0;
          padding-bottom: 0;
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
