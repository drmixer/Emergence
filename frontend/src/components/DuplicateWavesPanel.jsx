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

export default function DuplicateWavesPanel({ payload, title = 'Duplicate Waves', compact = false }) {
    const waves = Array.isArray(payload?.waves) ? payload.waves : []
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
                <div className="duplicate-wave-summary">
                    <span>{Number(summary.proposal_wave_count || 0).toLocaleString()} proposal waves</span>
                    <span>{Number(summary.forum_wave_count || 0).toLocaleString()} forum waves</span>
                    <span>{Number(summary.clustered_item_count || 0).toLocaleString()} clustered items</span>
                </div>
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
                                {!compact && String(representative.source || '') === 'forum' && Number(representative.id || 0) > 0 && (
                                    <Link className="duplicate-wave-link" to={`/messages?thread=${representative.id}`}>
                                        Open representative thread
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
