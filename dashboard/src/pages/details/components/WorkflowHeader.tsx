import { useState } from 'react'
import { RotateCcw, Square, Loader2 } from 'lucide-react'
import type { WorkflowInfo, Step } from '../../../lib/types'
import {
  humanizeWorkflowName,
  formatTimestamp,
  formatDuration,
  sumTokensIn,
  sumTokensOut,
  estimateCost,
  formatCost,
  countLlmCalls,
  countToolCalls,
  computeCostBreakdown,
  type CostBreakdownEntry,
} from '../../../lib/stepHelpers'
import { resumeWorkflow, cancelWorkflow } from '../../../lib/api'
import { showToast } from '../../../shared/Toast'
import { StatusBadge } from '../../../shared/workflowStatus'
import { CopyButton } from './right/CopyButton'

interface Props {
  workflow: WorkflowInfo
  steps: Step[]
  displayStatus: WorkflowInfo['status']
  onActionSuccess?: () => void
}

function StatItem({ label, value }: { label: string; value: string }) {
  return (
    <span>
      <span className="text-slate-500">{label}: </span>
      <span className="text-slate-300 font-medium">{value}</span>
    </span>
  )
}

function formatRate(perToken: number): string {
  return `$${(perToken * 1_000_000).toFixed(2)} / 1M`
}

function formatBreakdownCost(n: number): string {
  return `$${n.toFixed(4)}`
}

function CostBreakdownPanel({ breakdown }: { breakdown: CostBreakdownEntry[] }) {
  const total = breakdown.reduce((sum, e) => sum + (e.subtotal ?? 0), 0)
  return (
    <div
      role="tooltip"
      className="absolute top-full left-0 mt-1 z-50 w-[280px] bg-slate-900 border border-slate-700 rounded-md shadow-lg shadow-black/50 p-3 text-xs font-normal normal-case"
    >
      <div className="space-y-3">
        {breakdown.map((entry) => (
          <div key={entry.model}>
            <div className="text-slate-200 font-medium mb-1 break-all">
              {entry.model}
            </div>
            {entry.subtotal == null ? (
              <div className="pl-2 text-slate-500 italic">no pricing available</div>
            ) : (
              <div className="pl-2 grid grid-cols-[auto_1fr_auto] gap-x-2 gap-y-0.5 font-mono tabular-nums text-[11px]">
                <span className="text-slate-400">In:</span>
                <span className="text-slate-300">
                  {entry.inputTokens.toLocaleString()} × {formatRate(entry.inputRate!)}
                </span>
                <span className="text-slate-200 text-right">
                  = {formatBreakdownCost(entry.inputCost!)}
                </span>
                <span className="text-slate-400">Out:</span>
                <span className="text-slate-300">
                  {entry.outputTokens.toLocaleString()} × {formatRate(entry.outputRate!)}
                </span>
                <span className="text-slate-200 text-right">
                  = {formatBreakdownCost(entry.outputCost!)}
                </span>
              </div>
            )}
          </div>
        ))}
      </div>
      <div className="border-t border-slate-700 mt-3 pt-2 flex items-baseline justify-between font-mono tabular-nums">
        <span className="text-slate-400 text-xs">Total:</span>
        <span className="text-amber-300 text-xs font-medium">
          {formatBreakdownCost(total)}
        </span>
      </div>
    </div>
  )
}

function CostStat({ steps, cost }: { steps: Step[]; cost: number | null }) {
  const [open, setOpen] = useState(false)
  const breakdown = computeCostBreakdown(steps)
  return (
    <span
      className="relative"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onFocus={() => setOpen(true)}
      onBlur={() => setOpen(false)}
      tabIndex={breakdown.length > 0 ? 0 : -1}
    >
      <StatItem label="Cost" value={formatCost(cost)} />
      {open && breakdown.length > 0 && <CostBreakdownPanel breakdown={breakdown} />}
    </span>
  )
}

interface ActionButtonProps {
  icon: typeof RotateCcw
  label: string
  onClick: () => void
  enabled: boolean
  pending: boolean
  disabledReason: string
}

function ActionButton({
  icon: Icon,
  label,
  onClick,
  enabled,
  pending,
  disabledReason,
}: ActionButtonProps) {
  const disabled = !enabled || pending
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={enabled ? label : disabledReason}
      className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium border transition-colors ${
        disabled
          ? 'border-slate-800 text-slate-600 bg-slate-900 cursor-not-allowed opacity-60'
          : 'border-slate-700 text-slate-200 bg-slate-800 hover:bg-slate-700'
      }`}
    >
      {pending ? <Loader2 size={13} className="animate-spin" /> : <Icon size={13} />}
      {label}
    </button>
  )
}

export function WorkflowHeader({ workflow, steps, displayStatus, onActionSuccess }: Props) {
  const [pending, setPending] = useState<'resume' | 'cancel' | null>(null)

  const totalDuration =
    workflow.updated_at > workflow.created_at
      ? workflow.updated_at - workflow.created_at
      : null

  const tokensIn = sumTokensIn(steps)
  const tokensOut = sumTokensOut(steps)
  const attempts = workflow.attempts
  const cost = estimateCost(steps)
  const llmCalls = countLlmCalls(steps)
  const toolCalls = countToolCalls(steps)

  const canResume = workflow.status === 'ERROR' || workflow.status === 'CANCELLED'
  const canCancel = workflow.status === 'PENDING'

  const handleResume = async () => {
    setPending('resume')
    try {
      await resumeWorkflow(workflow.workflow_id)
      onActionSuccess?.()
      showToast('Workflow resumed')
    } catch (err) {
      showToast(
        'Resume failed',
        err instanceof Error ? err.message : 'Unknown error',
      )
    } finally {
      setPending(null)
    }
  }

  const handleCancel = async () => {
    setPending('cancel')
    try {
      await cancelWorkflow(workflow.workflow_id)
      onActionSuccess?.()
      showToast('Workflow cancel requested')
    } catch (err) {
      showToast(
        'Cancel failed',
        err instanceof Error ? err.message : 'Unknown error',
      )
    } finally {
      setPending(null)
    }
  }

  return (
    <div className="bg-slate-900 border-b border-slate-800 px-6 py-4">
      {/* Title row */}
      <div className="flex items-center gap-3 flex-wrap">
        <h1 className="text-xl font-semibold text-slate-50 tracking-tight">
          {humanizeWorkflowName(workflow.name)}
        </h1>
        <StatusBadge status={displayStatus} />
        <span className="flex items-center font-mono text-xs text-slate-400">
          {workflow.workflow_id}
          <CopyButton text={workflow.workflow_id} label="Copy workflow ID" />
        </span>

        <div className="ml-auto flex items-center gap-2">
          <ActionButton
            icon={RotateCcw}
            label="Resume"
            onClick={handleResume}
            enabled={canResume}
            pending={pending === 'resume'}
            disabledReason="Resume is only available for errored workflows."
          />
          <ActionButton
            icon={Square}
            label="Cancel"
            onClick={handleCancel}
            enabled={canCancel}
            pending={pending === 'cancel'}
            disabledReason="Cancel is only available for running workflows."
          />
        </div>
      </div>

      {/* Stats row */}
      <div className="flex items-center gap-5 mt-2.5 flex-wrap text-sm text-slate-400">
        <span title={`Created: ${formatTimestamp(workflow.created_at)}`}>
          Started {formatTimestamp(workflow.created_at)}
        </span>

        {totalDuration != null && (
          <StatItem label="Duration" value={formatDuration(totalDuration)} />
        )}

        {attempts != null && attempts > 0 && (
          <span className={`px-2 py-0.5 rounded-full text-xs font-medium border ${
            attempts === 1
              ? 'bg-slate-800 text-slate-400 border-slate-700'
              : 'bg-amber-500/15 text-amber-300 border-amber-500/30'
          }`}>
            Attempts: {attempts}
          </span>
        )}

        <StatItem
          label={llmCalls === 1 ? 'LLM call' : 'LLM calls'}
          value={String(llmCalls)}
        />

        <StatItem
          label={toolCalls === 1 ? 'Tool call' : 'Tool calls'}
          value={String(toolCalls)}
        />

        {(tokensIn > 0 || tokensOut > 0) && (
          <StatItem
            label="Tokens"
            value={`${tokensIn.toLocaleString()} in · ${tokensOut.toLocaleString()} out`}
          />
        )}

        <CostStat steps={steps} cost={cost} />
      </div>
    </div>
  )
}
