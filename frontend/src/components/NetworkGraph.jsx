import { useCallback, useEffect, useMemo, useState } from 'react'
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
import { formatAgentDisplayLabel } from '../utils/agentIdentity'
import { ALLY_BUCKET_CONFIG, RIVAL_BUCKET_CONFIG, getRelationshipBucketMaps } from '../utils/relationshipBuckets'

const personalityColors = {
    efficiency: { bg: '#3B82F6', border: '#1D4ED8' },
    equality: { bg: '#10B981', border: '#047857' },
    freedom: { bg: '#8B5CF6', border: '#6D28D9' },
    stability: { bg: '#F59E0B', border: '#B45309' },
    neutral: { bg: '#6B7280', border: '#374151' }
}

const tierColors = {
    1: '#FFD700',
    2: '#C0C0C0',
    3: '#CD7F32',
    4: '#6B7280'
}

const edgeColors = {
    communication: '#3B82F6',
    trade: '#F59E0B',
    voting: '#10B981'
}

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

function dataToFlow(agents, relationships, filters) {
    const connectionCounts = {}
    relationships.forEach((rel) => {
        if (!filters[rel.type]) return
        connectionCounts[rel.source_id] = (connectionCounts[rel.source_id] || 0) + 1
        connectionCounts[rel.target_id] = (connectionCounts[rel.target_id] || 0) + 1
    })

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
        .filter((rel) => filters[rel.type])
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

export default function NetworkGraph({ agents, relationships }) {
    const [selectedNode, setSelectedNode] = useState(null)
    const [filters, setFilters] = useState({
        communication: true,
        trade: true,
        voting: true
    })
    const [nodes, setNodes, onNodesChange] = useNodesState([])
    const [edges, setEdges, onEdgesChange] = useEdgesState([])

    useEffect(() => {
        if (agents.length === 0) return
        const { nodes: newNodes, edges: newEdges } = dataToFlow(agents, relationships, filters)
        setNodes(newNodes)
        setEdges(newEdges)
    }, [agents, relationships, filters, setNodes, setEdges])

    const onNodeClick = useCallback((_event, node) => {
        setSelectedNode(node)
        setEdges((eds) => eds.map((edge) => {
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
        setEdges((eds) => eds.map((edge) => ({
            ...edge,
            style: {
                ...edge.style,
                opacity: 0.6
            },
            animated: false
        })))
    }, [setEdges])

    const toggleFilter = (type) => {
        setFilters((prev) => ({
            ...prev,
            [type]: !prev[type]
        }))
    }

    const stats = useMemo(() => ({
        totalAgents: agents.length,
        totalConnections: edges.length,
        communication: relationships.filter((r) => r.type === 'communication').length,
        trade: relationships.filter((r) => r.type === 'trade').length,
        voting: relationships.filter((r) => r.type === 'voting').length
    }), [agents, edges.length, relationships])

    return (
        <>
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
                            {(() => {
                                const relationshipsData =
                                  selectedNode.data?.legibility?.relationships && typeof selectedNode.data.legibility.relationships === 'object'
                                    ? selectedNode.data.legibility.relationships
                                    : {}
                                const { allyBuckets, rivalBuckets } = getRelationshipBucketMaps(relationshipsData)
                                return (
                                    <>
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
                                            {selectedNode.data?.legibility?.archetype?.title && (
                                                <div className="stat-row">
                                                    <span>Archetype</span>
                                                    <span>{selectedNode.data.legibility.archetype.title}</span>
                                                </div>
                                            )}
                                            {selectedNode.data?.legibility?.danger?.label && (
                                                <div className="stat-row">
                                                    <span>Danger</span>
                                                    <span>{selectedNode.data.legibility.danger.label}</span>
                                                </div>
                                            )}
                                            {ALLY_BUCKET_CONFIG.map((bucket) => allyBuckets[bucket.key] ? (
                                                <div className="stat-row" key={bucket.key}>
                                                    <span>{bucket.shortLabel}</span>
                                                    <span>{allyBuckets[bucket.key].display_name}</span>
                                                </div>
                                            ) : null)}
                                            {RIVAL_BUCKET_CONFIG.map((bucket) => rivalBuckets[bucket.key] ? (
                                                <div className="stat-row" key={bucket.key}>
                                                    <span>{bucket.shortLabel}</span>
                                                    <span>{rivalBuckets[bucket.key].display_name}</span>
                                                </div>
                                            ) : null)}
                                        </div>
                                    </>
                                )
                            })()}
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
        </>
    )
}
