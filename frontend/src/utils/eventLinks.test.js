import { describe, expect, it } from 'vitest'
import { getEventHref, getEventSourceHref } from './eventLinks'

describe('eventLinks', () => {
  it('uses event_id when API payloads do not expose id', () => {
    const event = {
      event_id: 256831,
      event_type: 'tweet_posted',
      metadata: {
        runtime: { run_id: 'real-20260427T042539Z' },
      },
    }

    expect(getEventSourceHref(event)).toBe('/runs/real-20260427T042539Z?event=256831')
    expect(getEventHref(event)).toBe('/runs/real-20260427T042539Z?event=256831')
  })

  it('keeps contextual destinations separate from source evidence links', () => {
    const event = {
      id: 42,
      event_type: 'forum_post',
      metadata: {
        result: { message_id: 1541 },
        runtime: { run_id: 'real-20260427T042539Z' },
      },
    }

    expect(getEventHref(event)).toBe('/messages?tab=forum&thread=1541')
    expect(getEventSourceHref(event)).toBe('/runs/real-20260427T042539Z?event=42')
  })
})
