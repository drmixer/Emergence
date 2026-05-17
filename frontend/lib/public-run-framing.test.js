import { describe, expect, it } from 'vitest'
import { DEFAULT_PUBLIC_RUN_FRAMING, getPublicRunFraming } from './public-run-framing.js'

describe('public run framing', () => {
  it('keeps K11 as the default public canary frame', () => {
    expect(getPublicRunFraming(null)).toMatchObject({
      label: 'K11: First Public Canary',
      heading: 'Live AI civilization experiment',
      caveat: DEFAULT_PUBLIC_RUN_FRAMING.caveat,
    })
  })

  it('derives conservative labels from run metadata without claiming research certainty', () => {
    expect(
      getPublicRunFraming({
        run_id: 'real-k12-20260518',
        run_class: 'special_exploratory',
      }).label,
    ).toBe('Public Canary')

    expect(
      getPublicRunFraming({
        run_class: 'standard_72h',
        condition_name: 'Standard 72h Baseline',
      }).label,
    ).toBe('Standard 72h Baseline')
  })

  it('uses explicit public framing metadata when available', () => {
    const framing = getPublicRunFraming({
      public_framing: {
        label: 'K12: Second Public Canary',
        heading: 'Public canary follow-up',
        caveat: 'Exploratory public run; compare it with prior evidence.',
        watch_items: [{ label: 'Survival', detail: 'Active, dormant, and dead agents.' }],
      },
    })

    expect(framing.label).toBe('K12: Second Public Canary')
    expect(framing.heading).toBe('Public canary follow-up')
    expect(framing.caveat).toBe('Exploratory public run; compare it with prior evidence.')
    expect(framing.watchItems).toEqual([{ label: 'Survival', detail: 'Active, dormant, and dead agents.' }])
  })
})
