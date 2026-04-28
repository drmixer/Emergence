const directThreadEventTypes = new Set([
    'direct_message',
    'request_aid',
    'aid_request_received',
    'refuse_aid',
    'aid_refusal_received',
])

const forumThreadEventTypes = new Set([
    'forum_post',
    'forum_reply',
    'public_accusation',
])

const agentStatusEventTypes = new Set(['became_dormant', 'awakened', 'agent_died', 'agent_revived'])

function getMessageThreadId(event) {
    const metadata = event?.metadata && typeof event.metadata === 'object' ? event.metadata : {}
    const result = metadata?.result && typeof metadata.result === 'object' ? metadata.result : {}
    const direct = Number(result.message_id || metadata.message_id || 0)
    return Number.isFinite(direct) && direct > 0 ? direct : 0
}

function getEventRunId(event) {
    const metadata = event?.metadata && typeof event.metadata === 'object' ? event.metadata : {}
    const runtime = metadata?.runtime && typeof metadata.runtime === 'object' ? metadata.runtime : {}
    return String(runtime.run_id || metadata.run_id || '').trim()
}

export function getEventId(event) {
    const eventId = Number(event?.id || event?.event_id || 0)
    return Number.isFinite(eventId) && eventId > 0 ? eventId : 0
}

export function getEventSourceHref(event) {
    const eventId = getEventId(event)
    if (eventId <= 0) return ''
    const runId = getEventRunId(event)
    if (runId) {
        return `/runs/${encodeURIComponent(runId)}?event=${encodeURIComponent(String(eventId))}`
    }
    return `/timeline?event=${encodeURIComponent(String(eventId))}`
}

export function getEventHref(event) {
    const eventType = String(event?.event_type || '').trim()
    const agentNumber = Number(event?.agent_number || 0)
    const threadId = getMessageThreadId(event)

    if (threadId > 0 && directThreadEventTypes.has(eventType)) {
        return `/messages?tab=direct&thread=${threadId}`
    }

    if (threadId > 0 && forumThreadEventTypes.has(eventType)) {
        return `/messages?tab=forum&thread=${threadId}`
    }

    if (eventType === 'create_proposal') {
        return '/governance?tab=proposals'
    }

    if (eventType === 'law_passed' || eventType === 'vote' || eventType === 'proposal_resolved') {
        return '/governance'
    }

    if (eventType === 'trade' || eventType === 'request_aid' || eventType === 'reserve_aid') {
        return '/resources'
    }

    if (agentNumber > 0 && agentStatusEventTypes.has(eventType)) {
        return `/agents/${agentNumber}`
    }

    return getEventSourceHref(event)
}
