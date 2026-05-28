import { CheckCircle2, XCircle } from 'lucide-react'
import type { Step, WorkflowInfo, WorkflowStatus } from '../../../../lib/types'
import {
  formatRelativeTime,
  formatTimestamp,
  humanizeWorkflowName,
} from '../../../../lib/stepHelpers'
import { usePricingSyncedAt } from '../../../../lib/pricingStore'
import { Section } from './Section'
import { DefList } from './DefList'
import { CopyButton } from './CopyButton'
import { FinalAnswerCard } from '../FinalAnswerCard'

interface Props {
  workflow: WorkflowInfo
  steps: Step[]
  displayStatus: WorkflowStatus
}

const STATUS_STYLES: Record<WorkflowStatus, string> = {
  SUCCESS: 'bg-emerald-500/15 text-emerald-300 ring-1 ring-emerald-500/30',
  PENDING: 'bg-amber-500/15 text-amber-300 ring-1 ring-amber-500/30',
  ERROR: 'bg-red-500/15 text-red-300 ring-1 ring-red-500/30',
  CANCELLED: 'bg-slate-800 text-slate-400 ring-1 ring-slate-700',
  ENQUEUED: 'bg-blue-500/15 text-blue-300 ring-1 ring-blue-500/30',
}

function StatusBadge({ status }: { status: WorkflowStatus }) {
  const cls = STATUS_STYLES[status]
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium ${cls}`}>
      {status === 'SUCCESS' && <CheckCircle2 size={11} />}
      {status === 'ERROR' && <XCircle size={11} />}
      {status}
    </span>
  )
}

function FinalAnswerBody({
  status,
  output,
}: {
  status: WorkflowStatus
  output: string | null
}) {
  if (status === 'PENDING') {
    return (
      <p className="text-xs text-slate-500 italic">
        Workflow still running — final answer will appear when it completes.
      </p>
    )
  }
  if (output == null) {
    return <p className="text-xs text-slate-500 italic">No final answer captured.</p>
  }
  return (
    <div className="space-y-2">
      {status === 'ERROR' && (
        <p className="text-xs text-amber-300">
          Workflow errored — final answer may be partial.
        </p>
      )}
      <FinalAnswerCard output={output} />
    </div>
  )
}

function countAgents(steps: Step[]): { count: number; preflightOnly: boolean } {
  const distinct = new Set<string>()
  for (const step of steps) {
    if (step.agent_name) distinct.add(step.agent_name)
  }
  return { count: distinct.size, preflightOnly: distinct.size === 0 }
}

function uniqueModels(steps: Step[]): string[] {
  const seen = new Set<string>()
  const ordered: string[] = []
  for (const step of steps) {
    if (step.llm_model && !seen.has(step.llm_model)) {
      seen.add(step.llm_model)
      ordered.push(step.llm_model)
    }
  }
  return ordered
}

function ModelsCell({ models }: { models: string[] }) {
  if (models.length <= 3) {
    return <span>{models.join(', ')}</span>
  }
  return (
    <div>
      <div>{models.length} models</div>
      <div className="text-slate-400 mt-0.5 text-[11px] font-normal">
        {models.join(', ')}
      </div>
    </div>
  )
}

function PricingSyncedAt({ syncedAt }: { syncedAt: number | null }) {
  if (syncedAt == null) {
    return <span className="text-amber-400">Pricing not yet synced</span>
  }
  return (
    <span className="text-slate-400">
      Pricing synced {formatRelativeTime(syncedAt)}
    </span>
  )
}

export function WorkflowDefaultPanel({ workflow, steps, displayStatus }: Props) {
  const inputAvailable = false   // backend-blocked; field doesn't exist on WorkflowInfo yet
  const finalAnswerExpandedByDefault =
    displayStatus === 'SUCCESS' && workflow.output != null
  const attempts = workflow.attempts
  const agents = countAgents(steps)
  const models = uniqueModels(steps)
  const pricingSyncedAt = usePricingSyncedAt()

  const metadataRows: Array<[string, React.ReactNode]> = [
    [
      'Workflow ID',
      <span key="id" className="inline-flex items-center">
        <span className="break-all">{workflow.workflow_id}</span>
        <CopyButton text={workflow.workflow_id} label="Copy workflow ID" />
      </span>,
    ],
    ['Created', formatTimestamp(workflow.created_at)],
    ['Updated', formatTimestamp(workflow.updated_at)],
    ['Status', <StatusBadge key="status" status={displayStatus} />],
    ...(attempts != null && attempts > 0
      ? ([['Attempts', String(attempts)]] as Array<[string, React.ReactNode]>)
      : []),
    [
      'Agents',
      agents.preflightOnly ? 'Pre-flight only' : String(agents.count),
    ],
    ...(models.length > 0
      ? ([[
          models.length === 1 ? 'Model' : 'Models',
          <ModelsCell key="models" models={models} />,
        ]] as Array<[string, React.ReactNode]>)
      : []),
    ['Pricing', <PricingSyncedAt key="pricing" syncedAt={pricingSyncedAt} />],
  ]

  return (
    <div>
      {/* Header strip */}
      <div className="px-4 py-3 border-b border-slate-800 sticky top-0 bg-slate-900 z-10">
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-semibold text-slate-100 truncate flex-1">
            {humanizeWorkflowName(workflow.name)}
          </h2>
          <StatusBadge status={displayStatus} />
        </div>
      </div>

      {/* Workflow Input — backend-blocked */}
      <Section title="Workflow Input" defaultExpanded={inputAvailable}>
        <p className="text-xs text-slate-500 italic">
          Workflow input not yet available from the backend.
        </p>
      </Section>

      {/* Final Answer */}
      <Section title="Final Answer" defaultExpanded={finalAnswerExpandedByDefault}>
        <FinalAnswerBody status={displayStatus} output={workflow.output} />
      </Section>

      {/* Metadata */}
      <Section title="Metadata" defaultExpanded={false}>
        <DefList rows={metadataRows} />
      </Section>
    </div>
  )
}
