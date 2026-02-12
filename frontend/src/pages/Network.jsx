// Network Page - Agent Relationship Graph Visualization
import { useState, useEffect, useCallback, useMemo } from 'react'
import ReactFlow, {
    Background,
    Controls,
    MiniMap,
    useNodesState,
    useEdgesState,
    MarkerType,
    Panel,
    Handle,
    Position
} from 'reactflow'
import { api } from '../services/api'
import { formatAgentDisplayLabel } from '../utils/agentIdentity'

// Personality colors for nodes
const personalityColors = {
    efficiency: { bg: '#3B82F6', border: '#1D4ED8' },
    equality: { bg: '#10B981', border: '#047857' },
    freedom: { bg: '#8B5CF6', border: '#6D28D9' },
    stability: { bg: '#F59E0B', border: '#B45309' },
    neutral: { bg: '#6B7280', border: '#374151' }
}

// Tier colors for node rings
const tierColors = {
    1: '#FFD700',  // Gold
    2: '#C0C0C0',  // Silver
    3: '#CD7F32',  // Bronze
    4: '#6B7280'   // Default
}

// Edge colors by relationship type
const edgeColors = {
    communication: '#3B82F6',
    trade: '#F59E0B',
    voting: '#10B981'
}

// Custom node component for agents
function AgentNode({ data }) {
    const personality = data.personality_type || data.personality || 'neutral'
    const tier = data.tier || 3
    const colors = personalityColors[personality] || personalityColors.neutral

    return (
        <div
            className={`agent-node tier-${tier}`}
            style={{
                '--node-bg': colors.bg,
                '--node-border': colors.border,
                '--tier-color': tierColors[tier] || tierColors[4]
            }}
        >
            {/* Handles for edge connections - invisible but required */}
            <Handle type="target" position={Position.Top} style={{ opacity: 0 }} />
            <Handle type="source" position={Position.Bottom} style={{ opacity: 0 }} />

            <div className="node-inner">
                <span className="node-number">#{data.agent_number}</span>
                {data.display_name && (
                    <span className="node-name">{data.display_name}</span>
                )}
            </div>
            {data.connectionCount > 0 && (
                <div className="node-badge">{data.connectionCount}</div>
            )}
        </div>
    )
}

const nodeTypes = {
    agent: AgentNode
}

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

// Convert data to ReactFlow format
function dataToFlow(agents, relationships, filters) {
    // Count connections per agent
    const connectionCounts = {}
    relationships.forEach(rel => {
        if (!filters[rel.type]) return
        connectionCounts[rel.source_id] = (connectionCounts[rel.source_id] || 0) + 1
        connectionCounts[rel.target_id] = (connectionCounts[rel.target_id] || 0) + 1
    })

    // Position nodes in a circular layout
    const angleStep = (2 * Math.PI) / agents.length
    const radius = Math.min(400, agents.length * 15)

    const nodes = agents.map((agent, index) => {
        const angle = index * angleStep
        const x = 500 + radius * Math.cos(angle)
        const y = 400 + radius * Math.sin(angle)

        return {
            id: `agent-${agent.id}`,
            type: 'agent',
            position: { x, y },
            data: {
                ...agent,
                connectionCount: connectionCounts[agent.id] || 0
            }
        }
    })

    const edges = relationships
        .filter(rel => filters[rel.type])
        .map((rel, index) => ({
            id: `edge-${index}`,
            source: `agent-${rel.source_id}`,
            target: `agent-${rel.target_id}`,
            type: 'default',
            animated: false,
            style: {
                stroke: edgeColors[rel.type],
                strokeWidth: Math.min(rel.strength / 5 + 1, 4),
                opacity: 0.6
            },
            markerEnd: {
                type: MarkerType.ArrowClosed,
                color: edgeColors[rel.type]
            },
            data: {
                type: rel.type,
                strength: rel.strength
            }
        }))

    return { nodes, edges }
}

export default function Network() {
    const [agents, setAgents] = useState([])
    const [relationships, setRelationships] = useState([])
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState(null)
    const [selectedNode, setSelectedNode] = useState(null)
    const [filters, setFilters] = useState({
        communication: true,
        trade: true,
        voting: true
    })

    const [nodes, setNodes, onNodesChange] = useNodesState([])
    const [edges, setEdges, onEdgesChange] = useEdgesState([])

    // Load data
    useEffect(() => {
        async function loadData() {
            try {
                setError(null)
                const agentList = await api.getAgents()
                const agentsArr = Array.isArray(agentList) ? agentList : []

                const byIdToNumber = new Map()
                const byNumberToId = new Map()
                for (const a of agentsArr) {
                    byIdToNumber.set(Number(a.id), Number(a.agent_number))
                    byNumberToId.set(Number(a.agent_number), Number(a.id))
                }

                const [tradeEvents, dmEvents, voteEvents, replyEvents, proposals] = await Promise.all([
                    api.getEvents({ type: 'trade', limit: 500 }),
                    api.getEvents({ type: 'direct_message', limit: 500 }),
                    api.getEvents({ type: 'vote', limit: 500 }),
                    api.getEvents({ type: 'forum_reply', limit: 500 }),
                    api.fetch('/api/proposals?limit=200'),
                ])

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

    // Update nodes/edges when data or filters change
    useEffect(() => {
        if (agents.length > 0) {
            const { nodes: newNodes, edges: newEdges } = dataToFlow(agents, relationships, filters)
            setNodes(newNodes)
            setEdges(newEdges)
        }
    }, [agents, relationships, filters, setNodes, setEdges])

    const onNodeClick = useCallback((event, node) => {
        setSelectedNode(node)

        // Highlight connected edges
        setEdges(eds => eds.map(edge => {
            const isConnected = edge.source === node.id || edge.target === node.id
            return {
                ...edge,
                style: {
                    ...edge.style,
                    opacity: isConnected ? 1 : 0.2,
                    strokeWidth: isConnected ? (edge.style.strokeWidth || 2) + 1 : edge.style.strokeWidth
                },
                animated: isConnected
            }
        }))
    }, [setEdges])

    const onPaneClick = useCallback(() => {
        setSelectedNode(null)
        // Reset edge highlighting
        setEdges(eds => eds.map(edge => ({
            ...edge,
            style: {
                ...edge.style,
                opacity: 0.6
            },
            animated: false
        })))
    }, [setEdges])

    const toggleFilter = (type) => {
        setFilters(prev => ({
            ...prev,
            [type]: !prev[type]
        }))
    }

    // Stats for the sidebar
    const stats = useMemo(() => {
        const activeEdges = edges.filter(e => {
            const type = relationships.find((_, i) => `edge-${i}` === e.id)?.type
            return filters[type]
        })

        return {
            totalAgents: agents.length,
            totalConnections: activeEdges.length,
            communication: relationships.filter(r => r.type === 'communication').length,
            trade: relationships.filter(r => r.type === 'trade').length,
            voting: relationships.filter(r => r.type === 'voting').length
        }
    }, [agents, edges, relationships, filters])

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
            <div className="network-header">
                <div>
                    <h1>🔗 Relationship Network</h1>
                    <p className="network-subtitle">
                        Visualizing connections between {stats.totalAgents} agents
                    </p>
                </div>
            </div>

            <div className="network-container">
                <ReactFlow
                    nodes={nodes}
                    edges={edges}
                    onNodesChange={onNodesChange}
                    onEdgesChange={onEdgesChange}
                    onNodeClick={onNodeClick}
                    onPaneClick={onPaneClick}
                    nodeTypes={nodeTypes}
                    fitView
                    attributionPosition="bottom-left"
                >
                    <Background color="#333" gap={20} />
                    <Controls />
                    <MiniMap
                        nodeColor={(node) => {
                            const personality = node.data?.personality_type || 'neutral'
                            return personalityColors[personality]?.bg || '#6B7280'
                        }}
                        maskColor="rgba(0, 0, 0, 0.8)"
                    />

                    <Panel position="top-left" className="network-panel">
                        <h3>Relationship Types</h3>
                        <div className="filter-buttons">
                            <button
                                className={`filter-btn communication ${filters.communication ? 'active' : ''}`}
                                onClick={() => toggleFilter('communication')}
                            >
                                💬 Communication ({stats.communication})
                            </button>
                            <button
                                className={`filter-btn trade ${filters.trade ? 'active' : ''}`}
                                onClick={() => toggleFilter('trade')}
                            >
                                🔄 Trade ({stats.trade})
                            </button>
                            <button
                                className={`filter-btn voting ${filters.voting ? 'active' : ''}`}
                                onClick={() => toggleFilter('voting')}
                            >
                                🗳️ Voting ({stats.voting})
                            </button>
                        </div>
                    </Panel>

                    {selectedNode && (
                        <Panel position="top-right" className="selected-panel">
                            <h3>{formatAgentDisplayLabel(selectedNode.data)}</h3>
                            <div className="selected-stats">
                                <div className="stat-row">
                                    <span>Tier</span>
                                    <span className={`tier-badge tier-${selectedNode.data.tier}`}>
                                        Tier {selectedNode.data.tier}
                                    </span>
                                </div>
                                <div className="stat-row">
                                    <span>Personality</span>
                                    <span className={`personality-tag ${selectedNode.data.personality_type}`}>
                                        {selectedNode.data.personality_type}
                                    </span>
                                </div>
                                <div className="stat-row">
                                    <span>Connections</span>
                                    <span>{selectedNode.data.connectionCount}</span>
                                </div>
                            </div>
                        </Panel>
                    )}
                </ReactFlow>
            </div>

            <div className="network-legend">
                <div className="legend-section">
                    <h4>Node Colors (Personality)</h4>
                    <div className="legend-items">
                        {Object.entries(personalityColors).map(([name, colors]) => (
                            <div key={name} className="legend-item">
                                <span
                                    className="legend-dot"
                                    style={{ background: colors.bg }}
                                />
                                <span>{name}</span>
                            </div>
                        ))}
                    </div>
                </div>
                <div className="legend-section">
                    <h4>Edge Colors (Relationship)</h4>
                    <div className="legend-items">
                        {Object.entries(edgeColors).map(([name, color]) => (
                            <div key={name} className="legend-item">
                                <span
                                    className="legend-line"
                                    style={{ background: color }}
                                />
                                <span>{name}</span>
                            </div>
                        ))}
                    </div>
                </div>
                <div className="legend-section">
                    <h4>Node Ring (Tier)</h4>
                    <div className="legend-items">
                        <div className="legend-item">
                            <span className="legend-dot" style={{ background: tierColors[1] }} />
                            <span>Tier 1 (Gold)</span>
                        </div>
                        <div className="legend-item">
                            <span className="legend-dot" style={{ background: tierColors[2] }} />
                            <span>Tier 2 (Silver)</span>
                        </div>
                        <div className="legend-item">
                            <span className="legend-dot" style={{ background: tierColors[3] }} />
                            <span>Tier 3 (Bronze)</span>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    )
}
