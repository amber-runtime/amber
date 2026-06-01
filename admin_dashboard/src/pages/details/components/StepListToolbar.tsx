import { useEffect, useState } from 'react'
import { Search, UnfoldVertical, FoldVertical, X } from 'lucide-react'

interface Props {
  searchQuery: string
  onSearchChange: (q: string) => void
  onExpandAll: () => void
  onCollapseAll: () => void
}

const DEBOUNCE_MS = 150

export function StepListToolbar({
  searchQuery,
  onSearchChange,
  onExpandAll,
  onCollapseAll,
}: Props) {
  const [local, setLocal] = useState(searchQuery)

  // Sync down when the parent clears the query (e.g., via Escape).
  useEffect(() => {
    setLocal(searchQuery)
  }, [searchQuery])

  // Debounced commit upward.
  useEffect(() => {
    if (local === searchQuery) return
    const t = setTimeout(() => onSearchChange(local), DEBOUNCE_MS)
    return () => clearTimeout(t)
  }, [local, searchQuery, onSearchChange])

  return (
    <div className="sticky top-0 z-10 flex items-center gap-2 bg-slate-950/95 backdrop-blur-sm py-2">
      <div className="relative flex-1 min-w-0">
        <Search
          size={13}
          className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-500 pointer-events-none"
        />
        <input
          type="text"
          value={local}
          onChange={(e) => setLocal(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Escape') setLocal('')
          }}
          placeholder="Search steps"
          className="w-full bg-slate-900 border border-slate-800 rounded-md pl-7 pr-7 py-1.5 text-xs text-slate-200 placeholder:text-slate-500 focus:outline-none focus:ring-1 focus:ring-amber-500/50 focus:border-amber-500/50"
        />
        {local && (
          <button
            type="button"
            onClick={() => setLocal('')}
            title="Clear search"
            className="absolute right-1.5 top-1/2 -translate-y-1/2 p-0.5 rounded text-slate-500 hover:text-slate-300 hover:bg-slate-800"
          >
            <X size={12} />
          </button>
        )}
      </div>

      <button
        type="button"
        onClick={onExpandAll}
        title="Expand all groups"
        className="p-1.5 rounded-md border border-slate-800 bg-slate-900 text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-colors"
      >
        <UnfoldVertical size={13} />
      </button>
      <button
        type="button"
        onClick={onCollapseAll}
        title="Collapse all groups"
        className="p-1.5 rounded-md border border-slate-800 bg-slate-900 text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-colors"
      >
        <FoldVertical size={13} />
      </button>
    </div>
  )
}
