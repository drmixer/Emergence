const MAX_NETWORK_EDGES = 80
const MIN_EDGES_PER_TYPE = 16

const RELATIONSHIP_TYPES = ['communication', 'trade', 'voting']

function keyForEdge(sourceId, targetId, type) {
    return `${sourceId}:${targetId}:${type}`
}

function incrementEdge(map, sourceId, targetId, type, delta = 1) {
    const source = Number(sourceId || 0)
    const target = Number(targetId || 0)
    if (!source || !target || source === target || !RELATIONSHIP_TYPES.includes(type)) return
    const key = keyForEdge(source, target, type)
    const prev = map.get(key) || { source_id: source, target_id: target, type, strength: 0 }
    prev.strength += delta
    map.set(key, prev)
}

function agentInternalIdFromMessageParticipant(participant) {
    return Number(participant?.id || 0)
}

function agentNumberFromEventTarget(event, keys) {
    const metadata = event?.metadata && typeof event.metadata === 'object' ? event.metadata : {}
    const action = metadata?.action && typeof metadata.action === 'object' ? metadata.action : {}
    for (const key of keys) {
        const value = Number(action[key] || metadata[key] || 0)
        if (Number.isFinite(value) && value > 0) return value
    }
    return 0
}

function sortEdges(edges) {
    return [...edges].sort((a, b) => {
        const strengthDelta = Number(b.strength || 0) - Number(a.strength || 0)
        if (strengthDelta !== 0) return strengthDelta
        const typeDelta = RELATIONSHIP_TYPES.indexOf(a.type) - RELATIONSHIP_TYPES.indexOf(b.type)
        if (typeDelta !== 0) return typeDelta
        const sourceDelta = Number(a.source_id || 0) - Number(b.source_id || 0)
        if (sourceDelta !== 0) return sourceDelta
        return Number(a.target_id || 0) - Number(b.target_id || 0)
    })
}

export function selectNetworkEdges(edgeMap, maxEdges = MAX_NETWORK_EDGES) {
    const allEdges = sortEdges(Array.from(edgeMap.values()))
    const selected = []
    const selectedKeys = new Set()

    const addEdge = (edge) => {
        if (!edge || selected.length >= maxEdges) return
        const key = keyForEdge(edge.source_id, edge.target_id, edge.type)
        if (selectedKeys.has(key)) return
        selected.push(edge)
        selectedKeys.add(key)
    }

    for (const type of RELATIONSHIP_TYPES) {
        const edgesForType = allEdges.filter((edge) => edge.type === type)
        edgesForType.slice(0, MIN_EDGES_PER_TYPE).forEach(addEdge)
    }

    allEdges.forEach(addEdge)
    return selected
}

export function buildNetworkRelationships({
    agents = [],
    tradeEvents = [],
    voteEvents = [],
    proposals = [],
    directMessages = [],
    forumPosts = [],
    forumReplies = [],
    aidEvents = [],
    refusalEvents = [],
    accusationEvents = [],
    contestEvents = [],
    maxEdges = MAX_NETWORK_EDGES,
} = {}) {
    const agentsArr = Array.isArray(agents) ? agents : []
    const byIdToNumber = new Map()
    const byNumberToId = new Map()
    for (const agent of agentsArr) {
        byIdToNumber.set(Number(agent.id), Number(agent.agent_number))
        byNumberToId.set(Number(agent.agent_number), Number(agent.id))
    }

    const proposalAuthorById = new Map()
    if (Array.isArray(proposals)) {
        for (const proposal of proposals) {
            if (!proposal?.id || !proposal?.author?.agent_number) continue
            proposalAuthorById.set(Number(proposal.id), Number(proposal.author.agent_number))
        }
    }

    const edgeMap = new Map()

    if (Array.isArray(tradeEvents)) {
        for (const event of tradeEvents) {
            const sourceInternalId = Number(event.agent_id)
            const sourceAgentNumber = byIdToNumber.get(sourceInternalId)
            const recipientNumber = agentNumberFromEventTarget(event, ['recipient_agent_id', 'recipient_agent_number'])
            const targetInternalId = byNumberToId.get(recipientNumber)
            if (!sourceAgentNumber || !targetInternalId) continue
            incrementEdge(edgeMap, sourceInternalId, targetInternalId, 'trade', 1)
        }
    }

    const messageIndex = new Map()
    for (const message of [...(forumPosts || []), ...(forumReplies || [])]) {
        const id = Number(message?.id || 0)
        if (id > 0) messageIndex.set(id, message)
    }

    const processMessages = (messages, delta = 1) => {
        if (!Array.isArray(messages)) return
        for (const message of messages) {
            const sourceInternalId = agentInternalIdFromMessageParticipant(message?.author)
            const recipientInternalId = agentInternalIdFromMessageParticipant(message?.recipient)
            if (recipientInternalId > 0) {
                incrementEdge(edgeMap, sourceInternalId, recipientInternalId, 'communication', delta)
                continue
            }
            const parentId = Number(message?.parent_message_id || 0)
            if (parentId > 0) {
                const parent = messageIndex.get(parentId)
                const parentAuthorId = agentInternalIdFromMessageParticipant(parent?.author)
                if (parentAuthorId > 0) {
                    incrementEdge(edgeMap, sourceInternalId, parentAuthorId, 'communication', delta)
                }
            }
        }
    }

    processMessages(directMessages, 1)
    processMessages(forumReplies, 1)

    if (Array.isArray(voteEvents)) {
        for (const event of voteEvents) {
            const sourceInternalId = Number(event.agent_id)
            const proposalId = Number(event?.metadata?.action?.proposal_id)
            const authorNumber = proposalAuthorById.get(proposalId)
            const targetInternalId = byNumberToId.get(authorNumber)
            if (!targetInternalId) continue
            incrementEdge(edgeMap, sourceInternalId, targetInternalId, 'voting', 1)
        }
    }

    const processTargetedEvents = (events, delta = 1) => {
        if (!Array.isArray(events)) return
        for (const event of events) {
            const sourceInternalId = Number(event.agent_id)
            const targetNumber = agentNumberFromEventTarget(event, ['target_agent_id', 'target_agent_number'])
            const targetInternalId = byNumberToId.get(targetNumber)
            if (!targetInternalId) continue
            incrementEdge(edgeMap, sourceInternalId, targetInternalId, 'communication', delta)
        }
    }

    processTargetedEvents(aidEvents, 1)
    processTargetedEvents(refusalEvents, 1)
    processTargetedEvents(accusationEvents, 1)

    if (Array.isArray(contestEvents)) {
        for (const event of contestEvents) {
            const sourceInternalId = Number(event.agent_id)
            const proposalId = Number(event?.metadata?.action?.proposal_id)
            const authorNumber = proposalAuthorById.get(proposalId)
            const targetInternalId = byNumberToId.get(authorNumber)
            if (!targetInternalId) continue
            incrementEdge(edgeMap, sourceInternalId, targetInternalId, 'communication', 1)
        }
    }

    return selectNetworkEdges(edgeMap, maxEdges)
}
