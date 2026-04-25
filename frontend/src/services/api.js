/**
 * API Service - Handles all communication with the backend
 */

import { resolveApiBase } from '../../lib/api-base'

export { resolveApiBase }

const API_BASE = resolveApiBase()

class APIService {
    constructor(baseUrl) {
        this.baseUrl = baseUrl
    }

    async fetch(endpoint, options = {}) {
        const url = `${this.baseUrl}${endpoint}`
        const {
            headers: optionHeaders = {},
            quietErrors = false,
            quietStatusCodes = [],
            ...restOptions
        } = options

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
            const status = Number(error?.status || 0)
            const suppressLog = quietErrors || quietStatusCodes.includes(status)
            if (!suppressLog) {
                console.error(`API Error (${endpoint}):`, error)
            }
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
    async getMessages(limit = 50, messageType = null) {
        const params = new URLSearchParams()
        params.append('limit', String(limit))
        if (messageType) params.append('message_type', String(messageType))
        return this.fetch(`/api/messages?${params.toString()}`)
    }

    async getMessage(id) {
        return this.fetch(`/api/messages/${id}`)
    }

    async getMessageThread(id) {
        return this.fetch(`/api/messages/thread/${id}`)
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
        if (options?.includeRoutineHoldIdles) params.append('include_routine_hold_idles', 'true')

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

    async getBestMoments(limit = 6, hours = 72, minSalience = 55, runId = '') {
        const params = new URLSearchParams()
        params.append('limit', String(limit))
        params.append('hours', String(hours))
        params.append('min_salience', String(minSalience))
        if (runId) params.append('run_id', String(runId))
        return this.fetch(`/api/analytics/best-moments?${params.toString()}`)
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

    async getReplayStory(hours = 24, minSalience = 55, limit = 8, runId = '') {
        const params = new URLSearchParams()
        params.append('hours', String(hours))
        params.append('min_salience', String(minSalience))
        params.append('limit', String(limit))
        if (runId) params.append('run_id', String(runId))
        return this.fetch(`/api/analytics/plot-turns/replay-story?${params.toString()}`)
    }

    async getRunPlayback(runId, pageLimit = 500) {
        const cleanRunId = String(runId || '').trim()
        if (!cleanRunId) {
            throw new Error('runId is required')
        }

        let offset = 0
        let totalCount = null
        let items = []
        let basePayload = null

        while (totalCount === null || offset < totalCount) {
            const params = new URLSearchParams()
            params.append('limit', String(pageLimit))
            params.append('offset', String(offset))

            const payload = await this.fetch(`/api/analytics/runs/${encodeURIComponent(cleanRunId)}/playback?${params.toString()}`, {
                quietStatusCodes: [404],
            })
            if (!basePayload) {
                basePayload = payload && typeof payload === 'object' ? payload : {}
                totalCount = Number(basePayload?.total_count || 0)
            }

            const pageItems = Array.isArray(payload?.items) ? payload.items : []
            if (pageItems.length === 0) break

            items = items.concat(pageItems)
            offset += pageItems.length

            if (pageItems.length < pageLimit) break
        }

        return {
            ...(basePayload || {}),
            items,
            count: items.length,
            total_count: totalCount ?? items.length,
        }
    }

    async getLatestSummary(runId = '') {
        const params = new URLSearchParams()
        const cleanRunId = String(runId || '').trim()
        if (cleanRunId) params.append('run_id', cleanRunId)
        const query = params.toString() ? `?${params.toString()}` : ''
        return this.fetch(`/api/analytics/summaries/latest${query}`)
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

    async getRunReports(runId) {
        const cleanRunId = String(runId || '').trim()
        if (!cleanRunId) {
            throw new Error('runId is required')
        }
        return this.fetch(`/api/reports/runs/${encodeURIComponent(cleanRunId)}`)
    }

    async getRunsArchive(limit = 24) {
        const params = new URLSearchParams()
        params.append('limit', String(limit))
        return this.fetch(`/api/reports/archive/runs?${params.toString()}`)
    }

    async getConditionReports(conditionName) {
        const cleanCondition = String(conditionName || '').trim()
        if (!cleanCondition) {
            throw new Error('conditionName is required')
        }
        return this.fetch(`/api/reports/conditions/${encodeURIComponent(cleanCondition)}`)
    }

    getRunReportDownloadUrl(runId, artifactType, format = 'json') {
        const cleanRunId = String(runId || '').trim()
        const cleanArtifactType = String(artifactType || '').trim()
        const cleanFormat = String(format || '').trim() || 'json'
        if (!cleanRunId || !cleanArtifactType) {
            throw new Error('runId and artifactType are required')
        }
        const params = new URLSearchParams()
        params.append('artifact_type', cleanArtifactType)
        params.append('format', cleanFormat)
        return `${this.baseUrl}/api/reports/runs/${encodeURIComponent(cleanRunId)}/download?${params.toString()}`
    }

    getConditionReportDownloadUrl(conditionName, format = 'json') {
        const cleanCondition = String(conditionName || '').trim()
        const cleanFormat = String(format || '').trim() || 'json'
        if (!cleanCondition) {
            throw new Error('conditionName is required')
        }
        const params = new URLSearchParams()
        params.append('format', cleanFormat)
        return `${this.baseUrl}/api/reports/conditions/${encodeURIComponent(cleanCondition)}/download?${params.toString()}`
    }

    // Prediction markets
    async getPredictionMarkets(status = null, limit = 20) {
        const params = new URLSearchParams()
        if (status) params.append('status', status)
        if (limit) params.append('limit', String(limit))
        const query = params.toString() ? `?${params.toString()}` : ''
        return this.fetch(`/api/predictions/markets${query}`)
    }

    async getPredictionMe() {
        return this.fetch('/api/predictions/me', {
            credentials: 'include',
        })
    }

    async placePredictionBet(marketId, prediction, amount) {
        return this.fetch(`/api/predictions/markets/${marketId}/bet`, {
            method: 'POST',
            credentials: 'include',
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
                protocol_version: String(payload?.protocol_version || '').trim() || null,
                condition_name: String(payload?.condition_name || '').trim() || null,
                hypothesis_id: String(payload?.hypothesis_id || '').trim() || null,
                season_id: String(payload?.season_id || '').trim() || null,
                season_number: Number.isFinite(Number(payload?.season_number))
                    ? Number(payload.season_number)
                    : null,
                parent_run_id: String(payload?.parent_run_id || '').trim() || null,
                transfer_policy_version: String(payload?.transfer_policy_version || '').trim() || null,
                epoch_id: String(payload?.epoch_id || '').trim() || null,
                run_class: String(payload?.run_class || '').trim() || null,
                tuning_run: Boolean(payload?.tuning_run),
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

    // Social draft review
    async getTwitterStatus(token, adminUser = null) {
        return this.fetch('/api/twitter/status', {
            headers: this._adminHeaders(token, adminUser),
        })
    }

    async getTwitterDrafts(token, adminUser = null, status = 'pending_review', limit = 50, offset = 0) {
        const params = new URLSearchParams()
        params.append('status', String(status || 'pending_review'))
        params.append('limit', String(limit))
        params.append('offset', String(offset))
        return this.fetch(`/api/twitter/drafts?${params.toString()}`, {
            headers: this._adminHeaders(token, adminUser),
        })
    }

    async updateTwitterDraft(token, draftId, payload = {}, adminUser = null) {
        return this.fetch(`/api/twitter/drafts/${draftId}`, {
            method: 'PATCH',
            headers: this._adminHeaders(token, adminUser),
            body: JSON.stringify({
                status: String(payload?.status || '').trim(),
                review_note: String(payload?.review_note || '').trim() || null,
                posted_url: String(payload?.posted_url || '').trim() || null,
                external_post_id: String(payload?.external_post_id || '').trim() || null,
            }),
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

    async rebuildRunReportBundle(token, payload = {}, adminUser = null) {
        return this.fetch('/api/admin/archive/reports/rebuild', {
            method: 'POST',
            headers: this._adminHeaders(token, adminUser),
            body: JSON.stringify({
                run_id: String(payload?.run_id || '').trim(),
                condition_name: String(payload?.condition_name || '').trim() || null,
                season_number: Number.isFinite(Number(payload?.season_number))
                    ? Number(payload.season_number)
                    : null,
                actor_id: String(payload?.actor_id || '').trim() || null,
            }),
        })
    }

    // Public archive/articles
    async getArchiveArticles(limit = 20, offset = 0, contentType = 'all', tag = '') {
        const params = new URLSearchParams()
        params.append('limit', String(limit))
        params.append('offset', String(offset))
        if (contentType && String(contentType).toLowerCase() !== 'all') {
            params.append('content_type', String(contentType))
        }
        const tagValue = String(tag || '').trim()
        if (tagValue) params.append('tag', tagValue)
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
                messageCount: overview?.messages?.meaningful_total ?? overview?.messages?.total ?? 0,
                degradedFallbackMessageCount: overview?.messages?.degraded_fallback_total ?? 0,
                lawCount: overview?.laws?.total ?? 0,
                proposalCount: overview?.proposals?.total ?? 0,
                day: overview?.day_number ?? 0,
                lastActivity: overview?.events?.latest ?? null,
                simulationActive: overview?.scope?.simulation_active === true,
                activeRunId: overview?.scope?.active_run_id || '',
                lastCompletedRunId: overview?.scope?.last_completed_run_id || '',
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

async function fetchEventSnapshot(limit = 25) {
    const response = await fetch(`${API_BASE}/api/events?limit=${limit}`, {
        headers: {
            'Content-Type': 'application/json',
        },
    })
    if (!response.ok) {
        throw new Error(`Event polling failed: ${response.status}`)
    }
    const payload = await response.json()
    return Array.isArray(payload) ? payload : []
}

// Event subscription fallback using polling.
export function subscribeToEvents(onEvent, onError) {
    let closed = false
    let pollTimer = null
    let connected = false
    const seenIds = new Set()

    const emitEvents = (items) => {
        const ordered = [...items].sort((a, b) => {
            const aTime = new Date(a?.created_at || 0).getTime()
            const bTime = new Date(b?.created_at || 0).getTime()
            return aTime - bTime
        })

        for (const item of ordered) {
            const eventId = Number(item?.id || 0)
            if (eventId > 0 && seenIds.has(eventId)) continue
            if (eventId > 0) {
                seenIds.add(eventId)
            }
            onEvent({
                type: 'event',
                ...item,
            })
        }

        if (seenIds.size > 500) {
            const newestIds = ordered
                .map((item) => Number(item?.id || 0))
                .filter((value) => value > 0)
            seenIds.clear()
            newestIds.forEach((value) => seenIds.add(value))
        }
    }

    const poll = async () => {
        try {
            const items = await fetchEventSnapshot()
            if (!connected) {
                connected = true
                onEvent({ type: 'connected', transport: 'poll' })
            }
            if (items.length === 0) {
                onEvent({ type: 'snapshot_empty' })
            } else {
                emitEvents(items)
            }
        } catch (error) {
            connected = false
            console.error('Event polling error:', error)
            if (onError) onError(error)
        } finally {
            if (!closed) {
                pollTimer = window.setTimeout(poll, 10000)
            }
        }
    }

    poll()

    return () => {
        closed = true
        if (pollTimer) {
            window.clearTimeout(pollTimer)
        }
    }
}
