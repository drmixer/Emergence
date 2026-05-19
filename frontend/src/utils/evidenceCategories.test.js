import { describe, expect, it } from 'vitest'
import { buildEvidenceCategoryFilters, filterEvidenceByCategory, getEvidenceCategoryKey } from './evidenceCategories'

describe('evidence categories', () => {
  it('maps run evidence to viewer-facing categories', () => {
    expect(getEvidenceCategoryKey({ event_type: 'became_dormant' })).toBe('survival')
    expect(getEvidenceCategoryKey({ event_type: 'create_proposal' })).toBe('governance')
    expect(getEvidenceCategoryKey({ event_type: 'request_aid' })).toBe('aid_trade')
    expect(getEvidenceCategoryKey({ event_type: 'public_accusation' })).toBe('public_order')
    expect(getEvidenceCategoryKey({ event_type: 'world_event' })).toBe('system')
    expect(getEvidenceCategoryKey({ event_type: 'tweet_posted' })).toBe('other')
  })

  it('builds counts and filters items without dropping the all bucket', () => {
    const items = [
      { event_type: 'agent_died' },
      { event_type: 'law_passed' },
      { event_type: 'trade' },
      { event_type: 'trade' },
    ]

    const filters = buildEvidenceCategoryFilters(items)
    expect(filters.map((filter) => [filter.key, filter.count])).toEqual([
      ['all', 4],
      ['survival', 1],
      ['governance', 1],
      ['aid_trade', 2],
    ])
    expect(filterEvidenceByCategory(items, 'aid_trade')).toHaveLength(2)
    expect(filterEvidenceByCategory(items, 'all')).toHaveLength(4)
  })
})
