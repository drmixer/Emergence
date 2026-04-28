// Network Page - Agent Relationship Graph Visualization
import { Suspense, lazy, useEffect, useState } from 'react'
import { api } from '../services/api'
import NoActiveRunNotice from '../components/NoActiveRunNotice'
import { buildNetworkRelationships } from '../utils/networkEdges'
const NetworkGraph = lazy(() => import('../components/NetworkGraph'))

export default function Network() {
    const [agents, setAgents] = useState([])
    const [relationships, setRelationships] = useState([])
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState(null)
    const [scope, setScope] = useState(null)

    // Load data
    useEffect(() => {
        async function loadData() {
            try {
                setError(null)
                const [
                    overview,
                    agentList,
                    tradeEvents,
                    voteEvents,
                    proposals,
                    directMessages,
                    forumPosts,
                    forumReplies,
                    aidEvents,
                    refusalEvents,
                    accusationEvents,
                    contestEvents,
                ] = await Promise.all([
                    api.fetch('/api/analytics/overview').catch(() => null),
                    api.getAgents(),
                    api.getEvents({ type: 'trade', limit: 500 }),
                    api.getEvents({ type: 'vote', limit: 500 }),
                    api.fetch('/api/proposals?limit=200'),
                    api.getMessages(200, 'direct_message'),
                    api.getMessages(200, 'forum_post'),
                    api.getMessages(200, 'forum_reply'),
                    api.getEvents({ type: 'request_aid', limit: 500 }),
                    api.getEvents({ type: 'refuse_aid', limit: 500 }),
                    api.getEvents({ type: 'public_accusation', limit: 500 }),
                    api.getEvents({ type: 'contest_proposal', limit: 500 }),
                ])
                const agentsArr = Array.isArray(agentList) ? agentList : []
                setScope(overview?.scope || null)

                const edges = buildNetworkRelationships({
                    agents: agentsArr,
                    tradeEvents,
                    voteEvents,
                    proposals,
                    directMessages,
                    forumPosts,
                    forumReplies,
                    aidEvents,
                    refusalEvents,
                    accusationEvents,
                    contestEvents,
                })

                const involvedIds = new Set()
                edges.forEach(e => { involvedIds.add(e.source_id); involvedIds.add(e.target_id) })

                const selectedAgents = agentsArr
                    .filter(a => involvedIds.has(Number(a.id)))

                setAgents(selectedAgents)
                setRelationships(edges)
            } catch (error) {
                setError(error)
                setScope(null)
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

    if (scope?.simulation_active === false) {
        return (
            <div className="network-page">
                <div className="network-header">
                    <div>
                        <h1>🔗 Relationship Network</h1>
                        <p className="network-subtitle">No active run.</p>
                    </div>
                </div>
                <NoActiveRunNotice
                    message="The live relationship graph is hidden while no run is active, so closed-run interactions are not presented as current social structure."
                    lastCompletedRunId={scope?.last_completed_run_id}
                />
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
