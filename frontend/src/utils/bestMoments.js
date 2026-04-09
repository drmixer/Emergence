export function getMomentRunId(turn) {
  return String(turn?.run_id || turn?.metadata?.runtime?.run_id || '').trim()
}

export function getMomentEvidenceHref(turn) {
  const runId = getMomentRunId(turn)
  const eventId = Number(turn?.event_id || 0)
  if (!runId) return ''
  const safeRunId = encodeURIComponent(runId)
  return `/runs/${safeRunId}${eventId > 0 ? `?event=${eventId}` : ''}`
}

export function getMomentReplayHref(turn) {
  const eventId = Number(turn?.event_id || 0)
  const runId = getMomentRunId(turn)
  const params = new URLSearchParams()
  params.set('tab', 'replay')
  if (eventId > 0) params.set('event', String(eventId))
  if (runId) params.set('run', runId)
  return `/highlights?${params.toString()}`
}

export function getStoryReplayHref(runId = '') {
  const params = new URLSearchParams()
  params.set('tab', 'replay')
  params.set('mode', 'story60')
  if (runId) params.set('run', String(runId))
  return `/highlights?${params.toString()}`
}
