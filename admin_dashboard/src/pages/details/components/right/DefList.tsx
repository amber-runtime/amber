import type { ReactNode } from 'react'

interface Props {
  rows: Array<[string, ReactNode]>
}

export function DefList({ rows }: Props) {
  return (
    <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1.5 text-xs">
      {rows.map(([label, value], i) => (
        <div key={`${label}-${i}`} className="contents">
          <dt className="text-slate-400">{label}</dt>
          <dd className="text-slate-200 font-mono break-all">{value}</dd>
        </div>
      ))}
    </dl>
  )
}
