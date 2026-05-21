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
  if (!runId) {
    const params = new URLSearchParams()
    params.set('tab', 'replay')
    if (eventId > 0) params.set('event', String(eventId))
    return `/highlights?${params.toString()}`
  }
  const params = new URLSearchParams()
  params.set('mode', eventId > 0 ? 'timeline' : 'story60')
  if (eventId > 0) params.set('event', String(eventId))
  return `/runs/${encodeURIComponent(runId)}/replay?${params.toString()}`
}

export function getStoryReplayHref(runId = '') {
  if (runId) {
    return `/runs/${encodeURIComponent(String(runId))}/replay?mode=story60`
  }
  const params = new URLSearchParams()
  params.set('tab', 'replay')
  params.set('mode', 'story60')
  return `/highlights?${params.toString()}`
}

export function getTimelineReplayHref(runId = '') {
  if (runId) {
    return `/runs/${encodeURIComponent(String(runId))}/replay?mode=timeline`
  }
  const params = new URLSearchParams()
  params.set('tab', 'replay')
  params.set('mode', 'timeline')
  return `/highlights?${params.toString()}`
}

export function getWatchReplayHref(runId = '', eventId = 0) {
  const cleanRunId = String(runId || '').trim()
  const cleanEventId = Number(eventId || 0)
  const params = new URLSearchParams()
  if (cleanRunId) params.set('run', cleanRunId)
  if (cleanEventId > 0) params.set('event', String(cleanEventId))
  const query = params.toString()
  return query ? `/watch?${query}` : '/watch'
}
