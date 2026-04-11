function decodeEscapes(value) {
  return String(value || '')
    .replace(/\\"/g, '"')
    .replace(/\\n/g, '\n')
    .replace(/\\t/g, '\t')
    .replace(/\\\\/g, '\\')
    .trim()
}

function extractField(raw, fieldName) {
  const pattern = new RegExp(`"${fieldName}"\\s*:\\s*"([^]*)`, 'i')
  const match = String(raw || '').match(pattern)
  if (!match) return ''

  const remainder = match[1]
  let extracted = ''
  let escaped = false

  for (const char of remainder) {
    if (!escaped && char === '"') break
    if (char === '\\' && !escaped) {
      escaped = true
      extracted += char
      continue
    }
    escaped = false
    extracted += char
  }

  return decodeEscapes(extracted)
}

export function sanitizeVisibleMessageContent(value) {
  const raw = String(value || '').trim()
  if (!raw) return ''

  try {
    const parsed = JSON.parse(raw)
    if (parsed && typeof parsed === 'object') {
      if (typeof parsed.content === 'string' && parsed.content.trim()) {
        return parsed.content.trim()
      }
      if (typeof parsed.reasoning === 'string' && parsed.reasoning.trim()) {
        return parsed.reasoning.trim()
      }
    }
  } catch {
    // Fall through to partial extraction for truncated JSON-ish content.
  }

  if (raw.startsWith('{') && /"action"\s*:/.test(raw)) {
    const extractedContent = extractField(raw, 'content')
    if (extractedContent) return extractedContent

    const extractedReasoning = extractField(raw, 'reasoning')
    if (extractedReasoning) return extractedReasoning

    return 'Malformed model output hidden.'
  }

  return raw
}
