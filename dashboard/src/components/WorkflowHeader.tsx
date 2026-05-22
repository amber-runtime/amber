import { useState } from 'react'
import { Copy, Check } from 'lucide-react'
import type { WorkflowInfo, WorkflowStatus } from '../lib/types'
import {
  humanizeWorkflowName,
  formatTimestamp,
  formatDuration,
  sumTokens,
} from '../lib/stepHelpers'
import type { Step } from '../lib/types'

interface Props {
  workflow: WorkflowInfo
  steps: Step[]
}

const STATUS_STYLES: Record<WorkflowStatus, string> = {
  SUCCESS: 'bg-emerald-500/15 text-emerald-300 border border-emerald-500/30',
  PENDING: 'bg-amber-500/15 text-amber-300 border border-amber-500/30',
  ERROR: 'bg-red-500/15 text-red-300 border border-red-500/30',
  CANCELLED: 'bg-slate-800 text-slate-400 border border-slate-700',
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)
  const copy = () => {
    navigator.clipboard.writeText(text).catch(() => undefined)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }
  return (
    <button
      onClick={copy}
      className="ml-1.5 p-0.5 rounded hover:bg-slate-700 text-slate-500 hover:text-slate-300 transition-colors"
      title="Copy workflow ID"
    >
      {copied ? <Check size={12} /> : <Copy size={12} />}
    </button>
  )
}

export function WorkflowHeader({ workflow, steps }: Props) {
  const totalDuration =
    workflow.updated_at > workflow.created_at
      ? workflow.updated_at - workflow.created_at
      : null

  const completedSteps = steps.filter((s) => s.completed_at_epoch_ms != null)
  const totalTokens = sumTokens(steps)
  const recoveries = workflow.recovery_attempts ?? 0

  const shortId =
    workflow.workflow_id.length > 20
      ? `${workflow.workflow_id.slice(0, 8)}…${workflow.workflow_id.slice(-4)}`
      : workflow.workflow_id

  return (
    <div className="bg-slate-900 border-b border-slate-800 px-6 py-4">
      {/* Title row */}
      <div className="flex items-center gap-3 flex-wrap">
        <h1 className="text-xl font-semibold text-slate-50 tracking-tight">
          {humanizeWorkflowName(workflow.name)}
        </h1>
        <span
          className={`px-2.5 py-0.5 rounded-full text-xs font-semibold uppercase tracking-wide ${STATUS_STYLES[workflow.status]}`}
        >
          {workflow.status}
        </span>
        <span className="flex items-center font-mono text-xs text-slate-400 ml-auto">
          {shortId}
          <CopyButton text={workflow.workflow_id} />
        </span>
      </div>

      {/* Stats row */}
      <div className="flex items-center gap-5 mt-2.5 flex-wrap text-sm text-slate-400">
        <span title={`Created: ${formatTimestamp(workflow.created_at)}`}>
          Started {formatTimestamp(workflow.created_at)}
        </span>

        {totalDuration != null && (
          <StatItem label="Duration" value={formatDuration(totalDuration)} />
        )}

        <span
          className={
            recoveries > 0
              ? 'px-2 py-0.5 rounded-full text-xs font-medium bg-amber-500/15 text-amber-300 border border-amber-500/30'
              : 'text-slate-500 text-xs'
          }
        >
          {recoveries > 0 ? `Recovered ${recoveries}×` : '0 recoveries'}
        </span>

        <StatItem label="Steps" value={String(completedSteps.length)} />

        {totalTokens > 0 && (
          <StatItem
            label="Tokens"
            value={totalTokens.toLocaleString()}
          />
        )}
      </div>
    </div>
  )
}

function StatItem({ label, value }: { label: string; value: string }) {
  return (
    <span>
      <span className="text-slate-500">{label}: </span>
      <span className="text-slate-300 font-medium">{value}</span>
    </span>
  )
}
