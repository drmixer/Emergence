import { describe, expect, it } from 'vitest'
import {
  buildEvidenceCategoryFilters,
  buildEvidenceGroups,
  filterEvidenceByCategory,
  getEvidenceCategoryKey,
} from './evidenceCategories'

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

  it('groups repeated traces without dropping the underlying source items', () => {
    const items = [
      {
        event_id: 1,
        event_type: 'request_aid',
        title: 'Request Aid',
        description: 'Beacon requested 2 food from the common pool.',
        salience: 50,
      },
      {
        event_id: 2,
        event_type: 'request_aid',
        title: 'Request Aid',
        description: 'Cipher requested 1 energy from an ally.',
        salience: 80,
      },
      {
        event_id: 3,
        event_type: 'law_passed',
        title: 'Law Passed',
        description: 'Agents passed an aid floor law.',
        salience: 70,
      },
    ]

    const groups = buildEvidenceGroups(items)
    expect(groups).toHaveLength(2)
    expect(groups[0]).toMatchObject({
      title: 'Request Aid',
      count: 2,
      categoryKey: 'aid_trade',
    })
    expect(groups[0].lead.event_id).toBe(2)
    expect(groups[0].items.map((item) => item.event_id)).toEqual([1, 2])
    expect(groups[0].summaries).toEqual([
      'Beacon requested 2 food from the common pool.',
      'Cipher requested 1 energy from an ally.',
    ])
  })
})
