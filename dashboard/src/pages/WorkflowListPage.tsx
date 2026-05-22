import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { RefreshCw, CheckCircle2, XCircle, AlertCircle } from 'lucide-react'
import type { WorkflowSummary, WorkflowStatus } from '../lib/types'
import { useWorkflows } from '../lib/workflowContext'
import { triggerWorkflow } from '../lib/api'
import { NewWorkflowButton } from '../components/NewWorkflowButton'
import { NewWorkflowModal } from '../components/NewWorkflowModal'
import { showToast } from '../components/Toast'
import { humanizeWorkflowName, formatRelativeTime, formatDuration } from '../lib/stepHelpers'

const SHOW_RUN_BUTTON =
  import.meta.env.DEV || import.meta.env.VITE_SHOW_RUN_BUTTON === 'true'

type Filter = 'all' | 'completed' | 'running' | 'errored'

const FILTER_STATUS: Record<Filter, WorkflowStatus | null> = {
  all: null,
  completed: 'SUCCESS',
  running: 'PENDING',
  errored: 'ERROR',
}

const EMPTY_MESSAGES: Record<Filter, string> = {
  all: 'No workflows yet.',
  completed: 'No completed workflows.',
  running: 'No running workflows.',
  errored: 'No errored workflows.',
}

function StatusIcon({ status }: { status: WorkflowStatus }) {
  if (status === 'SUCCESS')
    return <CheckCircle2 size={15} className="text-emerald-400 shrink-0" />
  if (status === 'PENDING')
    return (
      <span className="relative flex h-3 w-3 shrink-0 mt-0.5">
        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75" />
        <span className="relative inline-flex rounded-full h-3 w-3 bg-amber-500" />
      </span>
    )
  if (status === 'ERROR')
    return <XCircle size={15} className="text-red-400 shrink-0" />
  return <span className="w-3.5 h-3.5 rounded-full bg-slate-600 shrink-0" />
}

function RecoveryPill({ count }: { count: number }) {
  if (count <= 0) return null
  return (
    <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-amber-500/15 text-amber-300 border border-amber-500/30 whitespace-nowrap">
      Recovered {count}×
    </span>
  )
}

function workflowDuration(w: WorkflowSummary, now: number): string {
  if (w.status === 'PENDING') {
    return formatDuration(Math.max(0, now - w.created_at))
  }
  const ms = (w.completed_at || now) - w.created_at
  if (ms <= 0) return '—'
  return formatDuration(ms)
}

export function WorkflowListPage() {
  const navigate = useNavigate()
  const { workflows, loading, error, refresh, prependWorkflow } = useWorkflows()
  const [filter, setFilter] = useState<Filter>('all')
  const [modalOpen, setModalOpen] = useState(false)
  const [now, setNow] = useState(Date.now())

  // Tick every second when any workflow is PENDING so durations update live
  useEffect(() => {
    const hasPending = workflows.some((w) => w.status === 'PENDING')
    if (!hasPending) return
    const timer = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(timer)
  }, [workflows])

  const counts = {
    all: workflows.length,
    completed: workflows.filter((w) => w.status === 'SUCCESS').length,
    running: workflows.filter((w) => w.status === 'PENDING').length,
    errored: workflows.filter((w) => w.status === 'ERROR').length,
  }

  const FILTER_LABELS: Record<Filter, string> = {
    all: `All (${counts.all})`,
    completed: `Completed (${counts.completed})`,
    running: `Running (${counts.running})`,
    errored: `Errored (${counts.errored})`,
  }

  const filtered = workflows.filter((w) => {
    const target = FILTER_STATUS[filter]
    return target === null || w.status === target
  })

  const handleNewWorkflow = async (agent: string, input: string, crashDemo: boolean) => {
    try {
      const result = await triggerWorkflow(agent, input, crashDemo)
      const optimistic: WorkflowSummary = {
        workflow_id: result.workflow_id,
        name: agent,
        status: 'PENDING',
        created_at: Date.now(),
        completed_at: Date.now(),
        recovery_attempts: null,
      }
      prependWorkflow(optimistic)
      setModalOpen(false)
      showToast('Workflow started', `${result.workflow_id.slice(0, 8)}…`)
    } catch (err) {
      throw err  // re-throw so modal can display the error
    }
  }

  return (
    <div className="min-h-screen bg-slate-950">
      {/* Header */}
      <div className="bg-slate-900 border-b border-slate-800 px-6 py-4">
        <div className="max-w-5xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="text-amber-500 font-semibold tracking-tight text-xl">Amber</span>
            <span className="text-slate-700 select-none">·</span>
            <h1 className="text-xl font-semibold text-slate-50 tracking-tight">Workflows</h1>
            <span className="px-2 py-0.5 rounded-full bg-slate-800 text-slate-400 text-xs font-medium">
              {counts.all}
            </span>
          </div>
          <div className="flex items-center gap-2">
            {SHOW_RUN_BUTTON && (
              <NewWorkflowButton onClick={() => setModalOpen(true)} />
            )}
            <button
              onClick={() => void refresh()}
              className="p-2 rounded-md hover:bg-slate-800 text-slate-400 hover:text-slate-200 transition-colors"
              title="Refresh"
            >
              <RefreshCw size={16} />
            </button>
          </div>
        </div>
      </div>

      <div className="max-w-5xl mx-auto px-6 py-5">
        {/* Filter chips */}
        <div className="flex items-center gap-2 mb-4 flex-wrap">
          {(Object.keys(FILTER_LABELS) as Filter[]).map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`px-3 py-1.5 rounded-full text-xs font-medium transition-colors ${
                filter === f
                  ? 'bg-amber-500 text-slate-950 font-medium'
                  : 'bg-slate-900 text-slate-300 border border-slate-800 hover:bg-slate-800'
              }`}
            >
              {FILTER_LABELS[f]}
            </button>
          ))}
        </div>

        {/* Loading state */}
        {loading && (
          <div className="flex items-center justify-center py-20 gap-3">
            <div className="w-5 h-5 border-2 border-amber-500 border-t-transparent rounded-full animate-spin" />
            <span className="text-sm text-slate-500">Loading workflows…</span>
          </div>
        )}

        {/* Error state */}
        {!loading && error && (
          <div className="bg-slate-900 border border-red-500/30 rounded-lg px-5 py-6 flex items-start gap-3">
            <AlertCircle size={16} className="text-red-400 shrink-0 mt-0.5" />
            <div className="flex-1 min-w-0">
              <p className="text-sm text-red-400 font-medium mb-1">Failed to load workflows</p>
              <p className="text-xs text-slate-500 font-mono">{error}</p>
            </div>
            <button
              onClick={() => void refresh()}
              className="shrink-0 px-3 py-1.5 text-xs bg-slate-800 border border-slate-700 text-slate-300 rounded hover:bg-slate-700 transition-colors"
            >
              Retry
            </button>
          </div>
        )}

        {/* List */}
        {!loading && !error && (
          <div className="bg-slate-900 border border-slate-800 rounded-lg overflow-hidden">
            {filtered.length === 0 ? (
              <div className="px-4 py-12 text-center text-sm text-slate-500">
                {EMPTY_MESSAGES[filter]}
              </div>
            ) : (
              <table className="w-full border-collapse">
                <thead>
                  <tr className="border-b border-slate-800">
                    <th className="pl-4 pr-2 py-2.5 w-8" />
                    <th className="pr-4 py-2.5 text-left text-xs font-medium text-slate-400 uppercase tracking-wide">
                      Workflow
                    </th>
                    <th className="pr-4 py-2.5 text-right text-xs font-medium text-slate-400 uppercase tracking-wide whitespace-nowrap">
                      Started
                    </th>
                    <th className="pr-4 py-2.5 text-right text-xs font-medium text-slate-400 uppercase tracking-wide">
                      Duration
                    </th>
                    <th className="pr-4 py-2.5 text-right text-xs font-medium text-slate-400 uppercase tracking-wide">
                      Recovery
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((w) => (
                    <tr
                      key={w.workflow_id}
                      onClick={() => navigate(`/workflows/${w.workflow_id}`)}
                      className="border-b last:border-b-0 border-slate-800 hover:bg-slate-800/50 cursor-pointer transition-colors"
                    >
                      <td className="pl-4 pr-2 py-3.5">
                        <StatusIcon status={w.status} />
                      </td>
                      <td className="pr-4 py-3.5 max-w-xs">
                        <p className="text-sm font-medium text-slate-50 truncate">
                          {humanizeWorkflowName(w.name)}
                        </p>
                        <span className="text-xs font-mono text-slate-500">
                          {w.workflow_id.slice(0, 8)}…{w.workflow_id.slice(-4)}
                        </span>
                      </td>
                      <td className="pr-4 py-3.5 text-xs text-slate-300 whitespace-nowrap text-right">
                        {formatRelativeTime(w.created_at)}
                      </td>
                      <td className="pr-4 py-3.5 text-xs font-mono text-slate-300 text-right whitespace-nowrap">
                        {workflowDuration(w, now)}
                      </td>
                      <td className="pr-4 py-3.5 text-right">
                        <RecoveryPill count={w.recovery_attempts ?? 0} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}
      </div>

      {modalOpen && (
        <NewWorkflowModal
          onClose={() => setModalOpen(false)}
          onSubmit={handleNewWorkflow}
        />
      )}
    </div>
  )
}
