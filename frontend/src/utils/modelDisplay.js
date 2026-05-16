const MODEL_TYPE_LABELS = {
  // OpenRouter-routed cohorts. Keep the route visible so these do not read as
  // direct provider assignments.
  or_gpt_oss_120b: 'OpenRouter: GPT-OSS 120B',
  or_qwen3_235b_a22b_2507: 'OpenRouter: Qwen3 235B A22B',
  or_deepseek_v3_2: 'OpenRouter: DeepSeek V3.2',
  or_deepseek_chat_v3_1: 'OpenRouter: DeepSeek Chat V3.1',
  or_gpt_oss_20b: 'OpenRouter: GPT-OSS 20B',
  or_qwen3_32b: 'OpenRouter: Qwen3 32B',
  or_mistral_small_3_1_24b_free: 'OpenRouter: Mistral Small 3.1 24B',

  // Google Vertex-routed Gemini cohorts.
  or_mistral_small_3_1_24b: 'Direct Mistral: Small',
  gm_gemini_2_5_flash: 'Google Vertex: Gemini 2.5 Flash',
  gm_gemini_2_0_flash: 'Google Vertex: Gemini 2.5 Flash cohort',
  gm_gemini_2_0_flash_lite: 'Google Vertex: Gemini 2.5 Flash Lite cohort',

  // Stabilized compatibility cohorts. The assignment key is historical; the
  // runtime route is Google Vertex Gemini in the current no-fallback configuration.
  or_gpt_oss_20b_free: 'Google Vertex: stabilized GPT-OSS cohort',
  or_qwen3_4b_free: 'Google Vertex: stabilized Qwen cohort',

  // Legacy keys retained for old rows/backfills. Avoid direct-looking badges.
  'claude-sonnet-4': 'Legacy routed cohort: Claude Sonnet key',
  'gpt-4o-mini': 'Legacy routed cohort: GPT-4o Mini key',
  'claude-haiku': 'Legacy routed cohort: Claude Haiku key',
  'llama-3.3-70b': 'Legacy routed cohort: Llama 3.3 key',
  'llama-3.1-8b': 'Legacy routed cohort: Llama 3.1 key',
  'gemini-flash': 'Legacy routed cohort: Gemini Flash key',
}

export function formatModelTypeLabel(modelType) {
  const cleanType = String(modelType || '').trim()
  if (!cleanType) return 'Unknown model cohort'
  return MODEL_TYPE_LABELS[cleanType] || cleanType
}

export { MODEL_TYPE_LABELS }
