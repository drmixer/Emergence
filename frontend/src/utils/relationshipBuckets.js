export const ALLY_BUCKET_CONFIG = [
  { key: 'trade_support', label: 'Trade / Support', shortLabel: 'Trade' },
  { key: 'conversation_coordination', label: 'Conversation / Coordination', shortLabel: 'Coordination' },
  { key: 'voting_alignment', label: 'Voting Alignment', shortLabel: 'Voting' },
]

export const RIVAL_BUCKET_CONFIG = [
  { key: 'open_conflict', label: 'Open Conflict', shortLabel: 'Conflict' },
  { key: 'voting_clash', label: 'Voting Clash', shortLabel: 'Voting clash' },
]

function asRelationshipArray(value) {
  return Array.isArray(value) ? value.filter((item) => item && typeof item === 'object') : []
}

function inferCategories(item, kind) {
  const explicit = Array.isArray(item?.categories) ? item.categories.filter((value) => typeof value === 'string') : []
  if (explicit.length > 0) return explicit

  const relationship = String(item?.relationship || '').toLowerCase()
  const evidence = String(item?.evidence || '').toLowerCase()
  const categories = []

  if (kind === 'ally') {
    if (relationship.includes('trade') || relationship.includes('revival') || evidence.includes('trade') || evidence.includes('revival')) {
      categories.push('trade_support')
    }
    if (
      relationship.includes('conversation')
      || relationship.includes('collaborator')
      || evidence.includes('direct message')
      || evidence.includes('forum reply')
    ) {
      categories.push('conversation_coordination')
    }
    if (relationship.includes('voting') || evidence.includes('supportive vote')) {
      categories.push('voting_alignment')
    }
    return categories
  }

  if (relationship.includes('conflict') || relationship.includes('rival') || evidence.includes('conflict')) {
    categories.push('open_conflict')
  }
  if (relationship.includes('voting') || evidence.includes('opposition vote')) {
    categories.push('voting_clash')
  }
  return categories
}

function deriveBucketMap(items, kind, config) {
  const bucketMap = Object.fromEntries(config.map(({ key }) => [key, null]))
  for (const item of items) {
    for (const category of inferCategories(item, kind)) {
      if (category in bucketMap && bucketMap[category] == null) {
        bucketMap[category] = item
      }
    }
  }
  return bucketMap
}

function normalizeBucketMap(value, kind, config) {
  if (!value || typeof value !== 'object') {
    return null
  }
  const bucketMap = Object.fromEntries(config.map(({ key }) => [key, null]))
  let hasValue = false
  for (const { key } of config) {
    const item = value[key]
    if (item && typeof item === 'object') {
      bucketMap[key] = item
      hasValue = true
    }
  }
  return hasValue ? bucketMap : null
}

export function getRelationshipBucketMaps(relationships) {
  const safeRelationships = relationships && typeof relationships === 'object' ? relationships : {}
  const allies = asRelationshipArray(safeRelationships.allies)
  const rivals = asRelationshipArray(safeRelationships.rivals)

  const allyBuckets =
    normalizeBucketMap(safeRelationships.ally_buckets, 'ally', ALLY_BUCKET_CONFIG)
    || deriveBucketMap(allies, 'ally', ALLY_BUCKET_CONFIG)
  const rivalBuckets =
    normalizeBucketMap(safeRelationships.rival_buckets, 'rival', RIVAL_BUCKET_CONFIG)
    || deriveBucketMap(rivals, 'rival', RIVAL_BUCKET_CONFIG)

  return { allyBuckets, rivalBuckets }
}
