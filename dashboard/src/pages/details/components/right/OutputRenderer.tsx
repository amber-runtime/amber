import { JsonBlock, normalizeOutputValue } from './JsonBlock'
import { SearchWebResultsBlock, toSearchResults } from './SearchWebResultsBlock'

interface Props {
  value: unknown
  maxHeight?: string
}

function PlainTextBlock({
  value,
  maxHeight = 'max-h-64',
}: {
  value: string
  maxHeight?: string
}) {
  return (
    <pre className={`bg-slate-950 border border-slate-800 rounded p-3 text-xs text-slate-300 overflow-x-auto ${maxHeight} overflow-y-auto whitespace-pre-wrap leading-relaxed`}>
      {value}
    </pre>
  )
}

export function OutputRenderer({ value, maxHeight }: Props) {
  const normalized = normalizeOutputValue(value)
  if (toSearchResults(normalized).length > 0) {
    return <SearchWebResultsBlock value={normalized} />
  }

  if (typeof normalized === 'string') {
    return <PlainTextBlock value={normalized} maxHeight={maxHeight} />
  }

  return <JsonBlock value={normalized} maxHeight={maxHeight} />
}
