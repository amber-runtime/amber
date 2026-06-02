import { formatDuration } from '../../../lib/stepHelpers'

interface Props {
  start: number
  end: number
}

const TICK_COUNT = 4

export function TimeAxis({ start, end }: Props) {
  const totalMs = Math.max(end - start, 1)
  const labels = Array.from({ length: TICK_COUNT }, (_, i) =>
    formatDuration(Math.round((totalMs * i) / (TICK_COUNT - 1))),
  )

  return (
    <div className="grid grid-cols-[minmax(180px,1fr)_minmax(0,3fr)_4rem] items-center gap-3 px-3 pt-1 pb-2">
      <div />
      <div className="flex justify-between text-[10px] text-slate-500 tabular-nums">
        {labels.map((label, i) => (
          <span key={i}>{label}</span>
        ))}
      </div>
      <div />
    </div>
  )
}
