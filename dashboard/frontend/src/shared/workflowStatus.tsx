import type { WorkflowStatus } from '../lib/types'

export const STATUS_STYLES: Record<WorkflowStatus, { label: string; className: string }> = {
  ENQUEUED:                       { label: 'Enqueued',           className: 'bg-blue-500/15 text-blue-300 border border-blue-500/30' },
  SUCCESS:                        { label: 'Success',            className: 'bg-emerald-500/15 text-emerald-300 border border-emerald-500/30' },
  PENDING:                        { label: 'Pending',            className: 'bg-amber-500/15 text-amber-300 border border-amber-500/30' },
  ERROR:                          { label: 'Error',              className: 'bg-red-500/15 text-red-300 border border-red-500/30' },
  CANCELLED:                      { label: 'Cancelled',          className: 'bg-slate-700/50 text-slate-400 border border-slate-600' },
  MAX_RECOVERY_ATTEMPTS_EXCEEDED: { label: 'Recovery exhausted', className: 'bg-red-500/15 text-red-300 border border-red-500/30' },
  DELAYED:                        { label: 'Delayed',            className: 'bg-blue-500/15 text-blue-300 border border-blue-500/30' },
}

export function StatusBadge({ status }: { status: WorkflowStatus }) {
  const styles = STATUS_STYLES[status] ?? STATUS_STYLES.CANCELLED
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${styles.className}`}>
      {styles.label}
    </span>
  )
}

export function RetriedPill({ attempts }: { attempts: number | null }) {
  if (attempts == null || attempts <= 1) return null
  return (
    <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium whitespace-nowrap bg-amber-500/15 text-amber-300 border border-amber-500/30">
      Retried
    </span>
  )
}
