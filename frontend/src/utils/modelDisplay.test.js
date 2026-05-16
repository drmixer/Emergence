import { describe, expect, it } from 'vitest'
import { formatModelTypeLabel } from './modelDisplay'

describe('model display labels', () => {
  it('makes OpenRouter-routed cohorts explicit', () => {
    expect(formatModelTypeLabel('or_gpt_oss_120b')).toBe('OpenRouter: GPT-OSS 120B')
    expect(formatModelTypeLabel('or_qwen3_235b_a22b_2507')).toBe('OpenRouter: Qwen3 235B A22B')
  })

  it('does not present stabilized compatibility cohorts as OpenRouter calls', () => {
    expect(formatModelTypeLabel('or_gpt_oss_20b_free')).toBe('Google Vertex: stabilized GPT-OSS cohort')
    expect(formatModelTypeLabel('or_qwen3_4b_free')).toBe('Google Vertex: stabilized Qwen cohort')
  })

  it('avoids direct-looking labels for legacy routed keys', () => {
    expect(formatModelTypeLabel('gpt-4o-mini')).toBe('Legacy routed cohort: GPT-4o Mini key')
    expect(formatModelTypeLabel('claude-sonnet-4')).toBe('Legacy routed cohort: Claude Sonnet key')
  })
})
