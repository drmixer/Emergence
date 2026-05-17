export const DEFAULT_PUBLIC_WATCH_ITEMS = [
  { label: 'Survival', detail: 'Who stays active, who goes dormant, who recovers, and who dies.' },
  { label: 'Aid & Trade', detail: 'Whether agents rescue each other, bargain, refuse, or hoard.' },
  { label: 'Laws', detail: 'What they propose, pass, contest, enforce, or ignore.' },
  { label: 'Public Order', detail: 'Accusations, sanctions, invalid actions, and conflict signals.' },
  { label: 'Model Behavior', detail: 'Cohort differences with routed provider and resolved model attribution.' },
]

export const DEFAULT_PUBLIC_RUN_FRAMING = {
  label: 'K11: First Public Canary',
  heading: 'Live AI civilization experiment',
  landingHeading: 'Live AI civilization experiment, not finished research.',
  caveat: 'Exploratory public run. One run can show signals; it does not prove broad conclusions.',
  landingCaveat: 'Exploratory public run. Watch the pressure live, then check the evidence before drawing broader conclusions.',
  sectionNote: 'An exploratory public run. Watch the pressure live, then judge it against the evidence before making broader claims.',
  watchItems: DEFAULT_PUBLIC_WATCH_ITEMS,
}

const SPECIAL_EXPLORATORY_CLASSES = new Set(['special_exploratory', 'tuning', 'public_canary'])

function cleanString(value) {
  return typeof value === 'string' ? value.trim() : ''
}

function pickString(...values) {
  for (const value of values) {
    const clean = cleanString(value)
    if (clean) {
      return clean
    }
  }
  return ''
}

function normalizeWatchItems(value) {
  if (!Array.isArray(value)) {
    return DEFAULT_PUBLIC_WATCH_ITEMS
  }

  const items = value
    .map((item) => ({
      label: pickString(item?.label, item?.title, item?.name),
      detail: pickString(item?.detail, item?.description, item?.copy),
    }))
    .filter((item) => item.label && item.detail)

  return items.length > 0 ? items : DEFAULT_PUBLIC_WATCH_ITEMS
}

function hasK11Signal(metadata) {
  const haystack = [
    metadata?.run_id,
    metadata?.condition_name,
    metadata?.hypothesis_id,
    metadata?.season_id,
    metadata?.epoch_id,
  ]
    .map((value) => cleanString(value).toLowerCase())
    .join(' ')

  return /\bk11\b/.test(haystack) || haystack.includes('first public canary')
}

function titleCaseRunClass(value) {
  return cleanString(value)
    .split(/[_-]+/g)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ')
}

function inferPublicLabel(metadata) {
  if (!metadata || typeof metadata !== 'object') {
    return DEFAULT_PUBLIC_RUN_FRAMING.label
  }

  if (hasK11Signal(metadata)) {
    return DEFAULT_PUBLIC_RUN_FRAMING.label
  }

  const runClass = cleanString(metadata.run_class).toLowerCase()
  if (SPECIAL_EXPLORATORY_CLASSES.has(runClass)) {
    return 'Public Canary'
  }

  const conditionName = cleanString(metadata.condition_name)
  if (conditionName) {
    return conditionName
  }

  const readableRunClass = titleCaseRunClass(runClass)
  return readableRunClass || DEFAULT_PUBLIC_RUN_FRAMING.label
}

export function getPublicRunFraming(metadata) {
  const framing = metadata?.public_framing || metadata?.publicFraming || {}

  const label = pickString(
    framing.label,
    framing.public_label,
    metadata?.public_label,
    metadata?.publicLabel,
    inferPublicLabel(metadata),
  )

  const heading = pickString(
    framing.heading,
    framing.title,
    metadata?.public_heading,
    metadata?.publicHeading,
    DEFAULT_PUBLIC_RUN_FRAMING.heading,
  )

  const landingHeading = pickString(
    framing.landing_heading,
    framing.landingHeading,
    metadata?.public_landing_heading,
    metadata?.publicLandingHeading,
    heading === DEFAULT_PUBLIC_RUN_FRAMING.heading ? DEFAULT_PUBLIC_RUN_FRAMING.landingHeading : heading,
  )

  const caveat = pickString(
    framing.caveat,
    framing.summary,
    metadata?.public_caveat,
    metadata?.publicCaveat,
    DEFAULT_PUBLIC_RUN_FRAMING.caveat,
  )

  const landingCaveat = pickString(
    framing.landing_caveat,
    framing.landingCaveat,
    metadata?.public_landing_caveat,
    metadata?.publicLandingCaveat,
    caveat === DEFAULT_PUBLIC_RUN_FRAMING.caveat ? DEFAULT_PUBLIC_RUN_FRAMING.landingCaveat : caveat,
  )

  return {
    label,
    heading,
    landingHeading,
    caveat,
    landingCaveat,
    sectionNote: pickString(
      framing.section_note,
      framing.sectionNote,
      metadata?.public_section_note,
      metadata?.publicSectionNote,
      DEFAULT_PUBLIC_RUN_FRAMING.sectionNote,
    ),
    watchItems: normalizeWatchItems(
      framing.watch_items || framing.watchItems || metadata?.public_watch_items || metadata?.publicWatchItems,
    ),
  }
}
