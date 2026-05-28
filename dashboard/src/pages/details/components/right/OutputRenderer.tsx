import { JsonBlock, normalizeOutputValue } from './JsonBlock'
import { SearchWebResultsBlock, toSearchResults } from './SearchWebResultsBlock'

interface Props {
  value: unknown
  maxHeight?: string
  textClassName?: string
}

function PlainTextBlock({
  value,
  maxHeight = 'max-h-64',
  textClassName = 'text-slate-300',
}: {
  value: string
  maxHeight?: string
  textClassName?: string
}) {
  return (
    <pre className={`bg-slate-950 border border-slate-800 rounded p-3 text-xs ${textClassName} overflow-x-auto ${maxHeight} overflow-y-auto whitespace-pre-wrap leading-relaxed`}>
      {value}
    </pre>
  )
}

export function OutputRenderer({ value, maxHeight, textClassName }: Props) {
  const normalized = normalizeOutputValue(value)
  if (toSearchResults(normalized).length > 0) {
    return <SearchWebResultsBlock value={normalized} />
  }

  if (typeof normalized === 'string') {
    return (
      <PlainTextBlock
        value={normalized}
        maxHeight={maxHeight}
        textClassName={textClassName}
      />
    )
  }

  return <JsonBlock value={normalized} maxHeight={maxHeight} />
}
