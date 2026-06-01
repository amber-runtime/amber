import { useState } from 'react'
import { Check, Copy } from 'lucide-react'

interface Props {
  text: string
  label?: string
}

export function CopyButton({ text, label = 'Copy' }: Props) {
  const [copied, setCopied] = useState(false)
  const copy = (e: React.MouseEvent) => {
    e.stopPropagation()
    navigator.clipboard.writeText(text).catch(() => undefined)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }
  return (
    <button
      type="button"
      onClick={copy}
      className="ml-1.5 p-0.5 rounded hover:bg-slate-700 text-slate-500 hover:text-slate-300 transition-colors"
      title={label}
    >
      {copied ? <Check size={12} /> : <Copy size={12} />}
    </button>
  )
}
