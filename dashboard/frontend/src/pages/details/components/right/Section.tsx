import { useState } from 'react'
import type { ReactNode } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'

interface Props {
  title: string
  defaultExpanded?: boolean
  children: ReactNode
}

export function Section({ title, defaultExpanded = true, children }: Props) {
  const [expanded, setExpanded] = useState(defaultExpanded)

  return (
    <div className="border-t border-slate-800">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="w-full flex items-center justify-between px-4 py-2 text-left hover:bg-slate-800/40 transition-colors"
      >
        <span className="text-sm font-medium text-slate-300">{title}</span>
        <span className="text-slate-600 shrink-0">
          {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </span>
      </button>
      {expanded && <div className="px-4 pb-4 pt-1">{children}</div>}
    </div>
  )
}
