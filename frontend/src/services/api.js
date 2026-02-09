/**
 * API Service - Handles all communication with the backend
 */

const API_BASE =
    (typeof globalThis !== 'undefined' && globalThis?.process?.env?.NEXT_PUBLIC_API_URL) ||
    ((typeof import.meta !== 'undefined' && import.meta.env?.VITE_API_URL) ? import.meta.env.VITE_API_URL : '') ||
    'http://localhost:8000'

export function getViewerUserId() {
    let userId = localStorage.getItem('emergence_user_id')
    if (!userId) {
        userId = `user_${Math.random().toString(36).slice(2, 15)}`
        localStorage.setItem('emergence_user_id', userId)
    }
    return userId
}

class APIService {
    constructor(baseUrl) {
        this.baseUrl = baseUrl
    }

    async fetch(endpoint, options = {}) {
        const url = `${this.baseUrl}${endpoint}`
        const { headers: optionHeaders = {}, ...restOptions } = options

        try {
            const response = await fetch(url, {
                ...restOptions,
                headers: {
                    'Content-Type': 'application/json',
                    ...optionHeaders,
                },
            })

            if (!response.ok) {
                let detail = ''
                try {
                    const errorPayload = await response.json()
                    if (errorPayload && typeof errorPayload.detail === 'string') {
                        detail = errorPayload.detail
                    }
                } catch {
                    // Ignore JSON parse failures for non-JSON error responses.
                }
                const suffix = detail ? `: ${detail}` : ''
                const error = new Error(`API error: ${response.status}${suffix}`)
                error.status = response.status
                error.detail = detail
                throw error
            }

            return response.json()
        } catch (error) {
            console.error(`API Error (${endpoint}):`, error)
            throw error
        }
    }

    _adminHeaders(token, adminUser = null) {
        const cleanToken = String(token || '').trim()
        const cleanUser = String(adminUser || '').trim()
        const headers = {}
        if (cleanToken) {
            headers.Authorization = `Bearer ${cleanToken}`
        }
        if (cleanUser) {
            headers['X-Admin-User'] = cleanUser
        }
        return headers
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

    async getCrisisStrip(limit = 6) {
        return this.fetch(`/api/analytics/crisis-strip?limit=${limit}`)
    }

    async getPlotTurns(limit = 8, hours = 48, minSalience = 60, runId = '') {
        const params = new URLSearchParams()
        params.append('limit', String(limit))
        params.append('hours', String(hours))
        params.append('min_salience', String(minSalience))
        if (runId) params.append('run_id', String(runId))
        return this.fetch(`/api/analytics/plot-turns?${params.toString()}`)
    }

    async getSocialDynamics(days = 7) {
        return this.fetch(`/api/analytics/social-dynamics?days=${days}`)
    }

    async getClassMobility(hours = 24) {
        return this.fetch(`/api/analytics/class-mobility?hours=${hours}`)
    }

    async getPlotTurnReplay(hours = 24, minSalience = 55, bucketMinutes = 30, limit = 220, runId = '') {
        const params = new URLSearchParams()
        params.append('hours', String(hours))
        params.append('min_salience', String(minSalience))
        params.append('bucket_minutes', String(bucketMinutes))
        params.append('limit', String(limit))
        if (runId) params.append('run_id', String(runId))
        return this.fetch(`/api/analytics/plot-turns/replay?${params.toString()}`)
    }

    async getRunDetail(runId, hoursFallback = 24, traceLimit = 12, minSalience = 55) {
        const cleanRunId = String(runId || '').trim()
        if (!cleanRunId) {
            throw new Error('runId is required')
        }
        const params = new URLSearchParams()
        params.append('hours_fallback', String(hoursFallback))
        params.append('trace_limit', String(traceLimit))
        params.append('min_salience', String(minSalience))
        return this.fetch(`/api/analytics/runs/${encodeURIComponent(cleanRunId)}?${params.toString()}`)
    }

    // Prediction markets
    async getPredictionMarkets(status = null, limit = 20) {
        const params = new URLSearchParams()
        if (status) params.append('status', status)
        if (limit) params.append('limit', String(limit))
        const query = params.toString() ? `?${params.toString()}` : ''
        return this.fetch(`/api/predictions/markets${query}`)
    }

    async getPredictionMe(userId = getViewerUserId()) {
        return this.fetch('/api/predictions/me', {
            headers: { 'x-user-id': userId },
        })
    }

    async placePredictionBet(marketId, prediction, amount, userId = getViewerUserId()) {
        return this.fetch(`/api/predictions/markets/${marketId}/bet`, {
            method: 'POST',
            headers: { 'x-user-id': userId },
            body: JSON.stringify({ prediction, amount }),
        })
    }

    // Admin / Ops
    async getAdminStatus(token, adminUser = null) {
        return this.fetch('/api/admin/status', {
            headers: this._adminHeaders(token, adminUser),
        })
    }

    async getAdminConfig(token, adminUser = null) {
        return this.fetch('/api/admin/config', {
            headers: this._adminHeaders(token, adminUser),
        })
    }

    async updateAdminConfig(token, updates, reason = '', adminUser = null) {
        return this.fetch('/api/admin/config', {
            method: 'PATCH',
            headers: this._adminHeaders(token, adminUser),
            body: JSON.stringify({
                updates,
                reason: String(reason || '').trim() || null,
            }),
        })
    }

    async getAdminAudit(token, limit = 50, offset = 0, adminUser = null) {
        return this.fetch(`/api/admin/audit?limit=${limit}&offset=${offset}`, {
            headers: this._adminHeaders(token, adminUser),
        })
    }

    async pauseSimulation(token, reason = '', adminUser = null) {
        return this.fetch('/api/admin/control/pause', {
            method: 'POST',
            headers: this._adminHeaders(token, adminUser),
            body: JSON.stringify({
                reason: String(reason || '').trim() || null,
            }),
        })
    }

    async resumeSimulation(token, reason = '', adminUser = null) {
        return this.fetch('/api/admin/control/resume', {
            method: 'POST',
            headers: this._adminHeaders(token, adminUser),
            body: JSON.stringify({
                reason: String(reason || '').trim() || null,
            }),
        })
    }

    async setDegradedRouting(token, enabled, reason = '', adminUser = null) {
        const endpoint = enabled ? '/api/admin/control/degrade' : '/api/admin/control/degrade/clear'
        return this.fetch(endpoint, {
            method: 'POST',
            headers: this._adminHeaders(token, adminUser),
            body: JSON.stringify({
                reason: String(reason || '').trim() || null,
            }),
        })
    }

    async setSimulationRunMode(token, mode, reason = '', adminUser = null) {
        return this.fetch('/api/admin/control/run-mode', {
            method: 'POST',
            headers: this._adminHeaders(token, adminUser),
            body: JSON.stringify({
                mode,
                reason: String(reason || '').trim() || null,
            }),
        })
    }

    async startSimulationRun(token, payload, adminUser = null) {
        return this.fetch('/api/admin/control/run/start', {
            method: 'POST',
            headers: this._adminHeaders(token, adminUser),
            body: JSON.stringify({
                mode: payload?.mode,
                run_id: String(payload?.run_id || '').trim() || null,
                reset_world: Boolean(payload?.reset_world),
                reason: String(payload?.reason || '').trim() || null,
            }),
        })
    }

    async stopSimulationRun(token, payload = {}, adminUser = null) {
        return this.fetch('/api/admin/control/run/stop', {
            method: 'POST',
            headers: this._adminHeaders(token, adminUser),
            body: JSON.stringify({
                clear_run_id: Boolean(payload?.clear_run_id),
                reason: String(payload?.reason || '').trim() || null,
            }),
        })
    }

    async resetDevWorld(token, reason = '', adminUser = null) {
        return this.fetch('/api/admin/control/run/reset-dev', {
            method: 'POST',
            headers: this._adminHeaders(token, adminUser),
            body: JSON.stringify({
                reason: String(reason || '').trim() || null,
            }),
        })
    }

    async getAdminRunMetrics(token, runId = '', hoursFallback = 24, adminUser = null) {
        const params = new URLSearchParams()
        if (runId) params.append('run_id', String(runId))
        params.append('hours_fallback', String(hoursFallback))
        const query = params.toString() ? `?${params.toString()}` : ''
        return this.fetch(`/api/admin/run/metrics${query}`, {
            headers: this._adminHeaders(token, adminUser),
        })
    }

    async getAdminKpiRollups(token, days = 14, refresh = true, adminUser = null) {
        const params = new URLSearchParams()
        params.append('days', String(days))
        params.append('refresh', refresh ? 'true' : 'false')
        return this.fetch(`/api/admin/kpi/rollups?${params.toString()}`, {
            headers: this._adminHeaders(token, adminUser),
        })
    }

    // Admin archive/articles
    async getAdminArchiveArticles(token, adminUser = null, status = 'all', limit = 200, offset = 0) {
        const params = new URLSearchParams()
        params.append('status', String(status || 'all'))
        params.append('limit', String(limit))
        params.append('offset', String(offset))
        return this.fetch(`/api/admin/archive/articles?${params.toString()}`, {
            headers: this._adminHeaders(token, adminUser),
        })
    }

    async createAdminArchiveArticle(token, payload, adminUser = null) {
        return this.fetch('/api/admin/archive/articles', {
            method: 'POST',
            headers: this._adminHeaders(token, adminUser),
            body: JSON.stringify(payload || {}),
        })
    }

    async updateAdminArchiveArticle(token, articleId, payload, adminUser = null) {
        return this.fetch(`/api/admin/archive/articles/${articleId}`, {
            method: 'PATCH',
            headers: this._adminHeaders(token, adminUser),
            body: JSON.stringify(payload || {}),
        })
    }

    async publishAdminArchiveArticle(token, articleId, payload = {}, adminUser = null) {
        return this.fetch(`/api/admin/archive/articles/${articleId}/publish`, {
            method: 'POST',
            headers: this._adminHeaders(token, adminUser),
            body: JSON.stringify({
                published_at: payload?.published_at || null,
                evidence_run_id: String(payload?.evidence_run_id || '').trim() || null,
            }),
        })
    }

    async unpublishAdminArchiveArticle(token, articleId, adminUser = null) {
        return this.fetch(`/api/admin/archive/articles/${articleId}/unpublish`, {
            method: 'POST',
            headers: this._adminHeaders(token, adminUser),
            body: JSON.stringify({}),
        })
    }

    async deleteAdminArchiveArticle(token, articleId, adminUser = null) {
        return this.fetch(`/api/admin/archive/articles/${articleId}`, {
            method: 'DELETE',
            headers: this._adminHeaders(token, adminUser),
        })
    }

    async generateWeeklyArchiveDraft(token, payload = {}, adminUser = null) {
        return this.fetch('/api/admin/archive/drafts/weekly', {
            method: 'POST',
            headers: this._adminHeaders(token, adminUser),
            body: JSON.stringify(payload || {}),
        })
    }

    // Public archive/articles
    async getArchiveArticles(limit = 20, offset = 0) {
        const params = new URLSearchParams()
        params.append('limit', String(limit))
        params.append('offset', String(offset))
        return this.fetch(`/api/archive/articles?${params.toString()}`)
    }

    async getArchiveArticleBySlug(slug) {
        return this.fetch(`/api/archive/articles/${encodeURIComponent(String(slug || '').trim())}`)
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
