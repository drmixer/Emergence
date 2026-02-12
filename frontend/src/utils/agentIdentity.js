export const AGENT_ALIAS_HELP_TEXT =
    'Aliases are immutable system-assigned codenames. Canonical identity remains Agent #NN for attribution, analytics, and cohort tracking.'

const IMMUTABLE_AGENT_CODENAMES = [
    'Tensor',
    'Vector',
    'Matrix',
    'Kernel',
    'Lambda',
    'Sigma',
    'Delta',
    'Axiom',
    'Cipher',
    'Syntax',
    'Node',
    'Orbit',
    'Helix',
    'Quanta',
    'Vertex',
    'Circuit',
    'Pixel',
    'Fractal',
    'Scalar',
    'Nexus',
    'Logic',
    'Nova',
    'Flux',
    'Prime',
    'Arc',
    'Prism',
    'Lattice',
    'Beacon',
    'Proto',
    'Chronon',
    'Relay',
    'Specter',
    'Glyph',
    'Synth',
    'Tempo',
    'Channel',
    'Segment',
    'Pivot',
    'Meridian',
    'Cascade',
    'Lumen',
    'Paradox',
    'Eigen',
    'Spectra',
    'Contour',
    'Monad',
    'Aegis',
    'Entropy',
    'Atlas',
    'Apex',
]

function normalizeAgentNumber(agentNumber) {
    const parsed = Number(agentNumber)
    if (!Number.isFinite(parsed)) return 0
    const whole = Math.trunc(parsed)
    return whole > 0 ? whole : 0
}

export function formatCanonicalAgentLabel(agentNumber) {
    const normalized = normalizeAgentNumber(agentNumber)
    if (normalized <= 0) return 'Agent'
    return `Agent #${String(normalized).padStart(2, '0')}`
}

export function formatAgentAlias(displayName) {
    if (typeof displayName !== 'string') return ''
    const trimmed = displayName.trim()
    return trimmed.length > 0 ? trimmed : ''
}

export function formatAgentDisplayLabel(agentLike) {
    if (!agentLike || typeof agentLike !== 'object') return 'Agent'

    const normalized = normalizeAgentNumber(agentLike.agent_number)
    const canonical = formatCanonicalAgentLabel(agentLike.agent_number)
    const explicitAlias = formatAgentAlias(agentLike.display_name ?? agentLike.agent_name)
    const fallbackAlias =
        normalized > 0
            ? `${IMMUTABLE_AGENT_CODENAMES[(normalized - 1) % IMMUTABLE_AGENT_CODENAMES.length]}-${String(normalized).padStart(2, '0')}`
            : ''
    const alias = explicitAlias || fallbackAlias

    if (!alias) return canonical
    if (canonical === 'Agent') return alias
    if (alias === canonical) return canonical
    return `${alias} (${canonical})`
}
