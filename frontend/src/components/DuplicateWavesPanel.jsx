import { Link } from 'react-router-dom'

function formatTimestamp(value) {
    if (!value) return ''
    const date = new Date(value)
    if (Number.isNaN(date.getTime())) return ''
    return date.toLocaleString()
}

function actorLabel(actor) {
    if (!actor) return ''
    const name = String(actor.display_name || '').trim()
    const number = Number(actor.agent_number || 0)
    if (name && number > 0) return `${name} (Agent #${number})`
    if (number > 0) return `Agent #${number}`
    return name
}

function waveTitle(wave) {
    const representative = wave?.representative || {}
    return representative.title || representative.text || 'Repeated content wave'
}

function itemSummary(item) {
    const actor = actorLabel(item?.actor)
    const timestamp = formatTimestamp(item?.created_at)
    const parts = []
    if (actor) parts.push(actor)
    if (timestamp) parts.push(timestamp)
    return parts.join(' · ')
}

export function duplicateWaveClusteredIds(payload) {
    const ids = new Set()
    const waves = Array.isArray(payload?.waves) ? payload.waves : []
    for (const wave of waves) {
        const representativeId = Number(wave?.representative?.id || 0)
        const items = Array.isArray(wave?.items) ? wave.items : []
        for (const item of items) {
            const id = Number(item?.id || 0)
            if (id > 0 && id !== representativeId) ids.add(id)
        }
    }
    return ids
}

export default function DuplicateWavesPanel({ payload, title = 'Duplicate Waves', compact = false }) {
    const waves = Array.isArray(payload?.waves) ? payload.waves : []
    const crossWaveActors = Array.isArray(payload?.cross_wave_actors) ? payload.cross_wave_actors : []
    const summary = payload?.summary || {}
    if (waves.length === 0) return null

    return (
        <div className="card duplicate-waves-card">
            <div className="card-header">
                <h3>{title}</h3>
                <span className="strip-meta">
                    {Number(summary.wave_count || waves.length).toLocaleString()} waves
                </span>
            </div>
            <div className="card-body">
                <p className="duplicate-wave-explainer">
                    Similar forum/proposal items are grouped here so repeated waves do not read as separate independent claims. Wave time ranges can span multiple threads; representative threads are samples, not the full cluster.
                </p>
                <div className="duplicate-wave-summary">
                    <span>{Number(summary.proposal_wave_count || 0).toLocaleString()} proposal waves</span>
                    <span>{Number(summary.forum_wave_count || 0).toLocaleString()} forum waves</span>
                    <span>{Number(summary.clustered_item_count || 0).toLocaleString()} clustered items</span>
                    {Number(summary.cross_wave_actor_count || 0) > 0 && (
                        <span>{Number(summary.cross_wave_actor_count || 0).toLocaleString()} cross-wave agents</span>
                    )}
                </div>
                {crossWaveActors.length > 0 && (
                    <div className="cross-wave-actors">
                        <div className="cross-wave-actors-head">
                            <strong>Cross-wave participation</strong>
                            <span>Agents appearing in multiple distinct waves</span>
                        </div>
                        <div className="cross-wave-actor-list">
                            {crossWaveActors.slice(0, compact ? 4 : 8).map((row) => {
                                const actor = row.actor || {}
                                const actorNumber = Number(actor.agent_number || 0)
                                return (
                                    <div key={actorNumber || actorLabel(actor)} className="cross-wave-actor-row">
                                        <span>{actorLabel(actor)}</span>
                                        <strong>
                                            {Number(row.wave_count || 0).toLocaleString()} waves
                                        </strong>
                                    </div>
                                )
                            })}
                        </div>
                    </div>
                )}
                <div className="duplicate-wave-list">
                    {waves.slice(0, compact ? 3 : 6).map((wave) => {
                        const actors = Array.isArray(wave.actors) ? wave.actors.map(actorLabel).filter(Boolean) : []
                        const representative = wave.representative || {}
                        const source = String(wave.source || '').replace(/_/g, ' ')
                        return (
                            <div key={wave.id} className="duplicate-wave-row">
                                <div className="duplicate-wave-row-head">
                                    <strong>{waveTitle(wave)}</strong>
                                    <span>{Number(wave.count || 0).toLocaleString()} {source} items</span>
                                </div>
                                <div className="duplicate-wave-meta">
                                    <span>{Number(wave.actor_count || 0).toLocaleString()} agents</span>
                                    {wave.first_at && wave.last_at && (
                                        <span>{formatTimestamp(wave.first_at)} - {formatTimestamp(wave.last_at)}</span>
                                    )}
                                    {Number(wave.degraded_fallback_count || 0) > 0 && (
                                        <span>{Number(wave.degraded_fallback_count).toLocaleString()} degraded fallback</span>
                                    )}
                                </div>
                                {!compact && actors.length > 0 && (
                                    <div className="duplicate-wave-actors">
                                        {actors.slice(0, 4).join(', ')}
                                    </div>
                                )}
                                {!compact && Array.isArray(wave.items) && wave.items.length > 0 && (
                                    <details className="duplicate-wave-samples">
                                        <summary>Show sampled cluster items</summary>
                                        <div className="duplicate-wave-sample-list">
                                            {wave.items.slice(0, 8).map((item) => (
                                                <div key={item.id} className="duplicate-wave-sample">
                                                    <div className="duplicate-wave-sample-meta">
                                                        #{item.id} {itemSummary(item)}
                                                    </div>
                                                    <p>{item.text}</p>
                                                </div>
                                            ))}
                                        </div>
                                        {Number(wave.count || 0) > wave.items.length && (
                                            <div className="duplicate-wave-sample-note">
                                                Showing {wave.items.length} of {Number(wave.count || 0).toLocaleString()} semantically grouped items.
                                            </div>
                                        )}
                                    </details>
                                )}
                                {!compact && String(representative.source || '') === 'forum' && Number(representative.id || 0) > 0 && (
                                    <Link className="duplicate-wave-link" to={`/messages?thread=${representative.id}`}>
                                        Open representative thread sample
                                    </Link>
                                )}
                            </div>
                        )
                    })}
                </div>
            </div>
        </div>
    )
}
