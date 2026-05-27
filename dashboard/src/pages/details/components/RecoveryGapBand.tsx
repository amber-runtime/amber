import type { Step, WorkflowInfo } from '../../../lib/types'
import { findLargestRecoveryGap } from '../../../lib/stepHelpers'

interface Props {
  workflow: WorkflowInfo
  steps: Step[]
  windowStart: number
  windowEnd: number
}

const STRIPE_GRADIENT =
  'repeating-linear-gradient(45deg, rgba(245, 158, 11, 0.10) 0, rgba(245, 158, 11, 0.10) 4px, transparent 4px, transparent 8px)'

export function RecoveryGapBand({
  workflow,
  steps,
  windowStart,
  windowEnd,
}: Props) {
  if ((workflow.attempts ?? 0) <= 1) return null

  const gap = findLargestRecoveryGap(steps)
  if (gap == null) return null

  const totalMs = Math.max(windowEnd - windowStart, 1)
  const leftPct = ((gap.start - windowStart) / totalMs) * 100
  const widthPct = ((gap.end - gap.start) / totalMs) * 100

  return (
    <div className="pointer-events-none absolute inset-0">
      <div className="grid grid-cols-[minmax(180px,1fr)_minmax(0,3fr)_4rem] gap-3 px-3 h-full">
        <div />
        <div className="relative h-full">
          <div
            title="Workflow process was down here. DBOS auto-recovered."
            className="pointer-events-auto absolute top-0 bottom-0 min-w-[2px] rounded-sm ring-1 ring-amber-500/15"
            style={{
              left: `${leftPct}%`,
              width: `${widthPct}%`,
              backgroundImage: STRIPE_GRADIENT,
            }}
          />
        </div>
        <div />
      </div>
    </div>
  )
}
