/**
 * API Service - Handles all communication with the backend
 */

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'

class APIService {
    constructor(baseUrl) {
        this.baseUrl = baseUrl
    }

    async fetch(endpoint, options = {}) {
        const url = `${this.baseUrl}${endpoint}`

        try {
            const response = await fetch(url, {
                headers: {
                    'Content-Type': 'application/json',
                    ...options.headers,
                },
                ...options,
            })

            if (!response.ok) {
                throw new Error(`API error: ${response.status}`)
            }

            return response.json()
        } catch (error) {
            console.error(`API Error (${endpoint}):`, error)
            throw error
        }
    }

    // Agents
    async getAgents(filters = {}) {
        const params = new URLSearchParams()
        if (filters.status) params.append('status', filters.status)
        if (filters.tier) params.append('tier', filters.tier)
        if (filters.model_type) params.append('model_type', filters.model_type)
        if (filters.personality_type) params.append('personality_type', filters.personality_type)

        const query = params.toString() ? `?${params}` : ''
        return this.fetch(`/api/agents${query}`)
    }

    async getAgent(id) {
        return this.fetch(`/api/agents/${id}`)
    }

    async getAgentActions(id, limit = 50) {
        return this.fetch(`/api/agents/${id}/actions?limit=${limit}`)
    }

    async getAgentMessages(id, limit = 50) {
        return this.fetch(`/api/agents/${id}/messages?limit=${limit}`)
    }

    async getAgentVotes(id, limit = 50) {
        return this.fetch(`/api/agents/${id}/votes?limit=${limit}`)
    }

    // Messages
    async getMessages(limit = 50) {
        return this.fetch(`/api/messages?limit=${limit}`)
    }

    async getMessage(id) {
        return this.fetch(`/api/messages/${id}`)
    }

    // Proposals
    async getProposals(status = null) {
        const query = status ? `?status=${status}` : ''
        return this.fetch(`/api/proposals${query}`)
    }

    async getProposal(id) {
        return this.fetch(`/api/proposals/${id}`)
    }

    // Laws
    async getLaws(active = null) {
        const query = active !== null ? `?active=${active}` : ''
        return this.fetch(`/api/laws${query}`)
    }

    async getLaw(id) {
        return this.fetch(`/api/laws/${id}`)
    }

    // Resources
    async getResources() {
        return this.fetch('/api/resources')
    }

    async getResourceHistory() {
        return this.fetch('/api/resources/history')
    }

    async getResourceDistribution() {
        return this.fetch('/api/resources/distribution')
    }

    // Events
    async getEvents(options = 100) {
        // Back-compat: allow `getEvents(100)` or `getEvents({ limit, offset, type })`
        if (typeof options === 'number') {
            return this.fetch(`/api/events?limit=${options}`)
        }

        const params = new URLSearchParams()
        if (options?.limit) params.append('limit', String(options.limit))
        if (options?.offset) params.append('offset', String(options.offset))
        if (options?.type) params.append('type', String(options.type))

        const query = params.toString() ? `?${params}` : ''
        return this.fetch(`/api/events${query}`)
    }

    // Analytics
    async getAnalyticsOverview() {
        return this.fetch('/api/analytics/overview')
    }

    async getFactions() {
        return this.fetch('/api/analytics/factions')
    }

    async getVotingBlocs() {
        return this.fetch('/api/analytics/voting')
    }

    async getWealthDistribution() {
        return this.fetch('/api/analytics/wealth')
    }

    // Landing Page Stats
    async getLandingStats() {
        try {
            const [health, overview] = await Promise.all([
                this.fetch('/health'),
                this.fetch('/api/analytics/overview'),
            ])

            return {
                activeAgents: overview?.agents?.active ?? health.active_agents ?? 0,
                totalAgents: overview?.agents?.total ?? health.total_agents ?? 100,
                messageCount: overview?.messages?.total ?? 0,
                lawCount: overview?.laws?.total ?? 0,
                proposalCount: overview?.proposals?.total ?? 0,
                day: overview?.day_number ?? 0,
                lastActivity: overview?.events?.latest ?? null,
            }
        } catch (error) {
            console.error('Failed to get landing stats:', error)
            return null
        }
    }

    // Health
    async getHealth() {
        return this.fetch('/health')
    }
}

export const api = new APIService(API_BASE)

// SSE Event Stream
export function subscribeToEvents(onEvent, onError) {
    const eventSource = new EventSource(`${API_BASE}/api/events/stream`)

    eventSource.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data)
            onEvent(data)
        } catch (e) {
            console.error('Failed to parse event:', e)
        }
    }

    eventSource.onerror = (error) => {
        console.error('SSE Error:', error)
        if (onError) onError(error)
    }

    return () => eventSource.close()
}
