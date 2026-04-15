// Network Page - Agent Relationship Graph Visualization
import { Suspense, lazy, useEffect, useState } from 'react'
import { api } from '../services/api'
const NetworkGraph = lazy(() => import('../components/NetworkGraph'))

function keyForEdge(sourceId, targetId, type) {
    return `${sourceId}:${targetId}:${type}`
}

function incrementEdge(map, sourceId, targetId, type, delta = 1) {
    if (!sourceId || !targetId || sourceId === targetId) return
    const key = keyForEdge(sourceId, targetId, type)
    const prev = map.get(key) || { source_id: sourceId, target_id: targetId, type, strength: 0 }
    prev.strength += delta
    map.set(key, prev)
}

export default function Network() {
    const [agents, setAgents] = useState([])
    const [relationships, setRelationships] = useState([])
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState(null)

    // Load data
    useEffect(() => {
        async function loadData() {
            try {
                setError(null)
                const [agentList, tradeEvents, dmEvents, voteEvents, replyEvents, proposals] = await Promise.all([
                    api.getAgents(),
                    api.getEvents({ type: 'trade', limit: 500 }),
                    api.getEvents({ type: 'direct_message', limit: 500 }),
                    api.getEvents({ type: 'vote', limit: 500 }),
                    api.getEvents({ type: 'forum_reply', limit: 500 }),
                    api.fetch('/api/proposals?limit=200'),
                ])
                const agentsArr = Array.isArray(agentList) ? agentList : []

                const byIdToNumber = new Map()
                const byNumberToId = new Map()
                for (const a of agentsArr) {
                    byIdToNumber.set(Number(a.id), Number(a.agent_number))
                    byNumberToId.set(Number(a.agent_number), Number(a.id))
                }

                const proposalAuthorById = new Map()
                if (Array.isArray(proposals)) {
                    for (const p of proposals) {
                        if (!p?.id || !p?.author?.agent_number) continue
                        proposalAuthorById.set(Number(p.id), Number(p.author.agent_number))
                    }
                }

                const parentMessageIds = new Set()
                if (Array.isArray(replyEvents)) {
                    for (const e of replyEvents) {
                        const parentId = e?.metadata?.action?.parent_message_id
                        if (parentId) parentMessageIds.add(Number(parentId))
                    }
                }

                const parentIds = Array.from(parentMessageIds).slice(0, 50)
                const parentMessages = await Promise.all(
                    parentIds.map(async (mid) => {
                        try {
                            const msg = await api.getMessage(mid)
                            return msg
                        } catch {
                            return null
                        }
                    })
                )
                const parentAuthorByMessageId = new Map()
                for (const msg of parentMessages) {
                    if (!msg?.id || !msg?.author?.agent_number) continue
                    parentAuthorByMessageId.set(Number(msg.id), Number(msg.author.agent_number))
                }

                const edgeMap = new Map()

                const processTradeOrDM = (events, type) => {
                    if (!Array.isArray(events)) return
                    for (const e of events) {
                        const srcInternalId = Number(e.agent_id)
                        const srcAgentNumber = byIdToNumber.get(srcInternalId)
                        const recipientNumber = Number(e?.metadata?.action?.recipient_agent_id)
                        const tgtInternalId = byNumberToId.get(recipientNumber)
                        if (!srcAgentNumber || !tgtInternalId) continue
                        incrementEdge(edgeMap, srcInternalId, tgtInternalId, type, 1)
                    }
                }

                processTradeOrDM(dmEvents, 'communication')
                processTradeOrDM(tradeEvents, 'trade')

                if (Array.isArray(voteEvents)) {
                    for (const e of voteEvents) {
                        const srcInternalId = Number(e.agent_id)
                        const proposalId = Number(e?.metadata?.action?.proposal_id)
                        const authorNumber = proposalAuthorById.get(proposalId)
                        const tgtInternalId = byNumberToId.get(authorNumber)
                        if (!tgtInternalId) continue
                        incrementEdge(edgeMap, srcInternalId, tgtInternalId, 'voting', 1)
                    }
                }

                if (Array.isArray(replyEvents)) {
                    for (const e of replyEvents) {
                        const srcInternalId = Number(e.agent_id)
                        const parentMessageId = Number(e?.metadata?.action?.parent_message_id)
                        const parentAuthorNumber = parentAuthorByMessageId.get(parentMessageId)
                        const tgtInternalId = byNumberToId.get(parentAuthorNumber)
                        if (!tgtInternalId) continue
                        incrementEdge(edgeMap, srcInternalId, tgtInternalId, 'communication', 1)
                    }
                }

                const edges = Array.from(edgeMap.values())
                    .sort((a, b) => b.strength - a.strength)
                    .slice(0, 80)

                const involvedIds = new Set()
                edges.forEach(e => { involvedIds.add(e.source_id); involvedIds.add(e.target_id) })

                const selectedAgents = agentsArr
                    .filter(a => involvedIds.has(Number(a.id)))
                    .slice(0, 40)

                setAgents(selectedAgents)
                setRelationships(edges)
            } catch (error) {
                setError(error)
                setAgents([])
                setRelationships([])
            } finally {
                setLoading(false)
            }
        }

        loadData()
    }, [])

    if (loading) {
        return (
            <div className="network-page">
                <div className="network-loading">
                    <div className="loading-spinner" />
                    <p>Loading network data...</p>
                </div>
            </div>
        )
    }

    if (error) {
        return (
            <div className="network-page">
                <div className="empty-state">Failed to load relationship network.</div>
            </div>
        )
    }

    if (agents.length === 0 || relationships.length === 0) {
        return (
            <div className="network-page">
                <div className="network-header">
                    <div>
                        <h1>🔗 Relationship Network</h1>
                        <p className="network-subtitle">No relationships yet.</p>
                    </div>
                </div>
                <div className="empty-state">Once agents start messaging, trading, and voting, their connections will appear here.</div>
            </div>
        )
    }

    return (
        <div className="network-page">
            <Suspense
                fallback={
                    <>
                        <div className="network-header">
                            <div>
                                <h1>🔗 Relationship Network</h1>
                                <p className="network-subtitle">Rendering graph…</p>
                            </div>
                        </div>
                        <div className="network-loading">
                            <div className="loading-spinner" />
                            <p>Loading network graph…</p>
                        </div>
                    </>
                }
            >
                <NetworkGraph agents={agents} relationships={relationships} />
            </Suspense>
        </div>
    )
}
