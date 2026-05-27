import { Search, X } from 'lucide-react'

interface Props {
  value: string
  onChange: (next: string) => void
  placeholder?: string
}

export function SearchInput({ value, onChange, placeholder = 'Search...' }: Props) {
  return (
    <div className="relative mb-4">
      <Search
        size={14}
        className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500 pointer-events-none"
      />
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full pl-9 pr-9 py-2 bg-slate-900 border border-slate-800 rounded-md text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:border-slate-700"
      />
      {value && (
        <button
          type="button"
          onClick={() => onChange('')}
          className="absolute right-2 top-1/2 -translate-y-1/2 p-1 rounded text-slate-500 hover:text-slate-300 hover:bg-slate-800"
          aria-label="Clear search"
        >
          <X size={14} />
        </button>
      )}
    </div>
  )
}
