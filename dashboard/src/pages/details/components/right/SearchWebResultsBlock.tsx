import { parseSearchWebOutput } from '../../../../lib/stepHelpers'

interface Props {
  value: unknown
}

export type SearchResult = { title: string; url: string; summary: string }

function hasSearchResultShape(value: unknown): value is SearchResult[] {
  return Array.isArray(value) && value.every((item) => {
    if (item == null || typeof item !== 'object') return false
    const record = item as Record<string, unknown>
    return (
      typeof record.title === 'string' &&
      (typeof record.url === 'string' ||
        typeof record.href === 'string' ||
        typeof record.summary === 'string' ||
        typeof record.body === 'string')
    )
  })
}

export function toSearchResults(value: unknown): SearchResult[] {
  if (typeof value === 'string') return parseSearchWebOutput(value)
  if (!hasSearchResultShape(value)) return []
  return value.map((item) => {
    const record = item as Record<string, unknown>
    return {
      title: String(record.title ?? ''),
      url: String(record.url ?? record.href ?? ''),
      summary: String(record.summary ?? record.body ?? ''),
    }
  })
}

// Renders search result payloads as title/url/summary cards.
// Callers should handle generic fallback rendering when no recognized shape matches.
export function SearchWebResultsBlock({ value }: Props) {
  const results = toSearchResults(value)
  if (results.length === 0) return null
  return (
    <div className="space-y-2">
      {results.map((r, i) => (
        <div key={i} className="bg-slate-950 border border-slate-800 rounded p-3 text-xs">
          <p className="text-slate-200 font-medium leading-snug">{r.title}</p>
          {r.url && (
            <a
              href={r.url}
              target="_blank"
              rel="noreferrer"
              className="text-amber-400 hover:text-amber-300 underline break-all text-[11px] font-mono"
            >
              {r.url}
            </a>
          )}
          {r.summary && (
            <p className="text-slate-400 mt-1.5 leading-relaxed">{r.summary}</p>
          )}
        </div>
      ))}
    </div>
  )
}
