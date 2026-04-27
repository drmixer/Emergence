import { describe, expect, it } from 'vitest'
import { buildNetworkRelationships, selectNetworkEdges } from './networkEdges'

function agent(id, agentNumber) {
    return {
        id,
        agent_number: agentNumber,
        display_name: `Agent ${agentNumber}`,
    }
}

describe('network edge construction', () => {
    it('preserves communication edges when voting edges dominate the graph', () => {
        const edgeMap = new Map()
        for (let i = 1; i <= 100; i += 1) {
            edgeMap.set(`vote-${i}`, {
                source_id: i,
                target_id: i + 100,
                type: 'voting',
                strength: 50,
            })
        }
        edgeMap.set('communication-1', {
            source_id: 1,
            target_id: 2,
            type: 'communication',
            strength: 1,
        })

        const selected = selectNetworkEdges(edgeMap, 80)

        expect(selected).toHaveLength(80)
        expect(selected.some((edge) => edge.type === 'communication')).toBe(true)
    })

    it('builds communication edges from direct messages, forum replies, aid refusals, accusations, and contests', () => {
        const agents = [agent(10, 1), agent(20, 2), agent(30, 3)]
        const proposals = [
            {
                id: 99,
                author: { id: 30, agent_number: 3 },
            },
        ]
        const forumPosts = [
            {
                id: 700,
                author: { id: 10, agent_number: 1 },
                message_type: 'forum_post',
            },
        ]
        const forumReplies = [
            {
                id: 701,
                author: { id: 20, agent_number: 2 },
                parent_message_id: 700,
                message_type: 'forum_reply',
            },
        ]
        const directMessages = [
            {
                id: 800,
                author: { id: 10, agent_number: 1 },
                recipient: { id: 20, agent_number: 2 },
                message_type: 'direct_message',
            },
        ]

        const edges = buildNetworkRelationships({
            agents,
            proposals,
            directMessages,
            forumPosts,
            forumReplies,
            aidEvents: [
                {
                    agent_id: 20,
                    metadata: { action: { target_agent_id: 1 } },
                },
            ],
            refusalEvents: [
                {
                    agent_id: 10,
                    metadata: { action: { target_agent_id: 2 } },
                },
            ],
            accusationEvents: [
                {
                    agent_id: 20,
                    metadata: { action: { target_agent_id: 3 } },
                },
            ],
            contestEvents: [
                {
                    agent_id: 10,
                    metadata: { action: { proposal_id: 99 } },
                },
            ],
        })

        const communicationEdges = edges.filter((edge) => edge.type === 'communication')

        expect(communicationEdges.length).toBeGreaterThanOrEqual(4)
        expect(communicationEdges).toEqual(
            expect.arrayContaining([
                expect.objectContaining({ source_id: 10, target_id: 20, type: 'communication' }),
                expect.objectContaining({ source_id: 20, target_id: 10, type: 'communication' }),
                expect.objectContaining({ source_id: 20, target_id: 30, type: 'communication' }),
                expect.objectContaining({ source_id: 10, target_id: 30, type: 'communication' }),
            ])
        )
    })
})
