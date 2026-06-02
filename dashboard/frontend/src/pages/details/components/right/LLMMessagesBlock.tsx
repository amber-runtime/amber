import { JsonBlock } from './JsonBlock'

// Content can be a plain string or an array of blocks like { type, text }.
function extractContentText(content: unknown): string | null {
  if (typeof content === 'string') return content
  if (Array.isArray(content)) {
    const parts = content
      .map((b) =>
        b && typeof b === 'object' && 'text' in b
          ? String((b as Record<string, unknown>).text)
          : null,
      )
      .filter(Boolean)
    return parts.length > 0 ? parts.join('\n') : null
  }
  return null
}

// Best-effort parse: returns null if the value doesn't look like a message array.
function parseLLMMessages(value: unknown): { role: string; text: string }[] | null {
  if (!Array.isArray(value)) return null
  const messages = value.flatMap((item) => {
    if (!item || typeof item !== 'object') return []
    const { role, content } = item as Record<string, unknown>
    if (typeof role !== 'string') return []
    const text = extractContentText(content)
    return text != null ? [{ role, text }] : []
  })
  return messages.length > 0 ? messages : null
}

interface Props {
  value: unknown
}

export function LLMMessagesBlock({ value }: Props) {
  const messages = parseLLMMessages(value)
  if (!messages) {
    return <JsonBlock value={value} />
  }
  return (
    <div className="space-y-2">
      {messages.map(({ role, text }, i) => (
        <div key={i} className="bg-slate-950 border border-slate-800 rounded p-3 text-xs">
          <span className="text-slate-500 font-mono uppercase text-[10px] tracking-wider">
            {role}
          </span>
          <pre className="mt-1.5 text-slate-300 whitespace-pre-wrap leading-relaxed">
            {text}
          </pre>
        </div>
      ))}
    </div>
  )
}
