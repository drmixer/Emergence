export const EVIDENCE_CATEGORY_ORDER = ['all', 'survival', 'governance', 'aid_trade', 'public_order', 'system', 'other']

export const EVIDENCE_CATEGORY_META = {
  all: {
    label: 'All',
    description: 'All currently visible evidence traces for this view.',
  },
  survival: {
    label: 'Survival',
    description: 'Deaths, dormancy, revival, and active-population pressure.',
  },
  governance: {
    label: 'Governance',
    description: 'Proposals, voting, laws, and enforcement decisions.',
  },
  aid_trade: {
    label: 'Aid / Trade',
    description: 'Aid requests, refusals, rescues, trades, and resource-flow signals.',
  },
  public_order: {
    label: 'Public Order',
    description: 'Accusations, sanctions, seizures, exile, contests, and conflict pressure.',
  },
  system: {
    label: 'Run-wide Events',
    description: 'Simulation-world events plus clearly separated runtime/protocol traces.',
  },
  other: {
    label: 'Other',
    description: 'Notable traces that do not fit the main viewer categories.',
  },
}

const SURVIVAL_EVENT_TYPES = new Set(['agent_died', 'became_dormant', 'agent_revived', 'awakened'])
const GOVERNANCE_EVENT_TYPES = new Set(['law_passed', 'proposal_resolved', 'create_proposal', 'vote', 'vote_enforcement'])
const AID_TRADE_EVENT_TYPES = new Set(['trade', 'request_aid', 'refuse_aid'])
const PUBLIC_ORDER_EVENT_TYPES = new Set([
  'public_accusation',
  'contest_proposal',
  'initiate_sanction',
  'initiate_seizure',
  'initiate_exile',
  'enforcement_initiated',
  'agent_sanctioned',
  'resources_seized',
  'agent_exiled',
])
const SYSTEM_EVENT_TYPES = new Set(['world_event', 'processing_error', 'system_event'])

export function getEvidenceCategoryKey(item) {
  const eventType = String(item?.event_type || '').trim()
  const category = String(item?.category || '').trim()

  if (SURVIVAL_EVENT_TYPES.has(eventType)) return 'survival'
  if (GOVERNANCE_EVENT_TYPES.has(eventType) || category === 'governance') return 'governance'
  if (AID_TRADE_EVENT_TYPES.has(eventType) || category === 'cooperation' || category === 'alliance') return 'aid_trade'
  if (PUBLIC_ORDER_EVENT_TYPES.has(eventType) || category === 'conflict' || category === 'public_order') return 'public_order'
  if (SYSTEM_EVENT_TYPES.has(eventType) || category === 'crisis' || category === 'system') return 'system'
  return 'other'
}

export function buildEvidenceCategoryFilters(items) {
  const list = Array.isArray(items) ? items : []
  const counts = new Map(EVIDENCE_CATEGORY_ORDER.map((key) => [key, 0]))
  counts.set('all', list.length)
  list.forEach((item) => {
    const key = getEvidenceCategoryKey(item)
    counts.set(key, (counts.get(key) || 0) + 1)
  })

  return EVIDENCE_CATEGORY_ORDER
    .filter((key) => key === 'all' || (counts.get(key) || 0) > 0)
    .map((key) => ({
      key,
      label: EVIDENCE_CATEGORY_META[key]?.label || key,
      description: EVIDENCE_CATEGORY_META[key]?.description || '',
      count: counts.get(key) || 0,
    }))
}

export function filterEvidenceByCategory(items, categoryKey) {
  const list = Array.isArray(items) ? items : []
  const key = String(categoryKey || 'all')
  if (key === 'all') return list
  return list.filter((item) => getEvidenceCategoryKey(item) === key)
}

function getEvidenceEventType(item) {
  return String(item?.event_type || item?.category || 'event').trim().toLowerCase()
}

function getEvidenceTitle(item) {
  return String(item?.title || item?.event_type || item?.category || 'Run event').trim()
}

function normalizeEvidenceGroupText(value) {
  return String(value || '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, ' ')
    .trim()
}

function getEvidenceGroupKey(item) {
  const categoryKey = getEvidenceCategoryKey(item)
  const eventType = getEvidenceEventType(item)
  const title = normalizeEvidenceGroupText(getEvidenceTitle(item)) || eventType
  return `${categoryKey}:${eventType}:${title}`
}

function getEvidenceSalience(item) {
  const salience = Number(item?.salience)
  return Number.isFinite(salience) ? salience : 0
}

function summarizeEvidenceGroup(items) {
  const seen = new Set()
  const summaries = []
  ;(Array.isArray(items) ? items : []).forEach((item) => {
    const summary = String(item?.description || item?.summary || '').replace(/\s+/g, ' ').trim()
    const key = normalizeEvidenceGroupText(summary)
    if (!summary || seen.has(key)) return
    seen.add(key)
    summaries.push(summary)
  })
  return summaries.slice(0, 3)
}

export function buildEvidenceGroups(items) {
  const list = Array.isArray(items) ? items : []
  const groups = []
  const groupMap = new Map()

  list.forEach((item, index) => {
    const key = getEvidenceGroupKey(item)
    const existing = groupMap.get(key)
    if (existing) {
      existing.items.push(item)
      if (getEvidenceSalience(item) > getEvidenceSalience(existing.lead)) {
        existing.lead = item
      }
      return
    }

    const group = {
      key,
      categoryKey: getEvidenceCategoryKey(item),
      eventType: getEvidenceEventType(item),
      title: getEvidenceTitle(item),
      lead: item,
      firstIndex: index,
      items: [item],
    }
    groupMap.set(key, group)
    groups.push(group)
  })

  return groups
    .sort((left, right) => left.firstIndex - right.firstIndex)
    .map((group) => ({
      ...group,
      count: group.items.length,
      summaries: summarizeEvidenceGroup(group.items),
    }))
}
