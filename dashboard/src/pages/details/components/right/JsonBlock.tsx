// Recursively parse JSON strings nested inside arrays/objects.
// Lets us render LLM/tool payloads that arrive as JSON-in-JSON legibly.
export function normalizeOutputValue(value: unknown): unknown {
  if (typeof value === 'string') {
    try { return normalizeOutputValue(JSON.parse(value)) } catch { return value }
  }
  if (Array.isArray(value)) return value.map(normalizeOutputValue)
  if (value !== null && typeof value === 'object')
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>).map(([k, v]) => [k, normalizeOutputValue(v)])
    )
  return value
}

export function prettyOutput(value: unknown): string {
  try {
    return JSON.stringify(normalizeOutputValue(value), null, 2)
  } catch {
    return 'Unable to render'
  }
}

interface Props {
  value: unknown
  maxHeight?: string  // tailwind class, e.g. 'max-h-64'
}

export function JsonBlock({ value, maxHeight = 'max-h-64' }: Props) {
  return (
    <pre className={`bg-slate-950 border border-slate-800 rounded p-3 text-xs text-slate-300 overflow-x-auto ${maxHeight} overflow-y-auto leading-relaxed`}>
      {prettyOutput(value)}
    </pre>
  )
}
