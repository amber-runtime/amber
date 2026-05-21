import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { RefreshCw, CheckCircle2, XCircle } from 'lucide-react'
import type { WorkflowSummary, WorkflowStatus } from '../lib/types'
import { mockWorkflowList } from '../lib/mockData'
import {
  humanizeWorkflowName,
  formatRelativeTime,
  formatDuration,
  extractWorkflowInputArg,
} from '../lib/stepHelpers'

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
    return <CheckCircle2 size={15} className="text-green-500 shrink-0" />
  if (status === 'PENDING')
    return (
      <span className="relative flex h-3 w-3 shrink-0 mt-0.5">
        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75" />
        <span className="relative inline-flex rounded-full h-3 w-3 bg-amber-500" />
      </span>
    )
  if (status === 'ERROR')
    return <XCircle size={15} className="text-red-500 shrink-0" />
  return <span className="w-3.5 h-3.5 rounded-full bg-gray-300 shrink-0" />
}

function RecoveryPill({ count }: { count: number }) {
  if (count <= 0) return null
  return (
    <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-amber-50 text-amber-700 ring-1 ring-amber-200 whitespace-nowrap">
      Recovered {count}×
    </span>
  )
}

function workflowDuration(w: WorkflowSummary): string {
  if (w.status === 'PENDING') return 'running…'
  const ms = w.updated_at - w.created_at
  if (ms <= 0) return '—'
  return formatDuration(ms)
}

export function WorkflowListPage() {
  const navigate = useNavigate()
  const [filter, setFilter] = useState<Filter>('all')

  const counts = {
    all: mockWorkflowList.length,
    completed: mockWorkflowList.filter((w) => w.status === 'SUCCESS').length,
    running: mockWorkflowList.filter((w) => w.status === 'PENDING').length,
    errored: mockWorkflowList.filter((w) => w.status === 'ERROR').length,
  }

  const FILTER_LABELS: Record<Filter, string> = {
    all: `All (${counts.all})`,
    completed: `Completed (${counts.completed})`,
    running: `Running (${counts.running})`,
    errored: `Errored (${counts.errored})`,
  }

  const filtered = mockWorkflowList.filter((w) => {
    const target = FILTER_STATUS[filter]
    return target === null || w.status === target
  })

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white border-b border-gray-200 px-6 py-4">
        <div className="max-w-5xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="text-amber-500 font-bold tracking-tight text-xl">Amber</span>
            <span className="text-gray-300 select-none">·</span>
            <h1 className="text-xl font-semibold text-slate-900 tracking-tight">
              Workflows
            </h1>
            <span className="px-2 py-0.5 rounded-full bg-gray-100 text-gray-600 text-xs font-medium">
              {counts.all}
            </span>
          </div>
          <button
            className="p-2 rounded-md hover:bg-gray-100 text-gray-400 hover:text-gray-600 transition-colors"
            title="Refresh"
          >
            <RefreshCw size={16} />
          </button>
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
                  ? 'bg-amber-500 text-white'
                  : 'bg-white text-gray-600 border border-gray-200 hover:border-gray-300 hover:text-gray-800'
              }`}
            >
              {FILTER_LABELS[f]}
            </button>
          ))}
        </div>

        {/* List */}
        <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
          {filtered.length === 0 ? (
            <div className="px-4 py-12 text-center text-sm text-gray-400">
              {EMPTY_MESSAGES[filter]}
            </div>
          ) : (
            <table className="w-full border-collapse">
              <thead>
                <tr className="border-b border-gray-100">
                  <th className="pl-4 pr-2 py-2.5 w-8" />
                  <th className="pr-4 py-2.5 text-left text-xs font-medium text-gray-400 uppercase tracking-wide">
                    Workflow
                  </th>
                  <th className="pr-4 py-2.5 text-right text-xs font-medium text-gray-400 uppercase tracking-wide whitespace-nowrap">
                    Started
                  </th>
                  <th className="pr-4 py-2.5 text-right text-xs font-medium text-gray-400 uppercase tracking-wide">
                    Duration
                  </th>
                  <th className="pr-4 py-2.5 text-right text-xs font-medium text-gray-400 uppercase tracking-wide">
                    Steps
                  </th>
                  <th className="pr-4 py-2.5 text-right text-xs font-medium text-gray-400 uppercase tracking-wide">
                    Recovery
                  </th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((w) => (
                  <tr
                    key={w.workflow_id}
                    onClick={() => navigate(`/workflows/${w.workflow_id}`)}
                    className="border-b last:border-b-0 border-gray-100 hover:bg-gray-50 cursor-pointer transition-colors"
                  >
                    <td className="pl-4 pr-2 py-3.5">
                      <StatusIcon status={w.status} />
                    </td>
                    <td className="pr-4 py-3.5 max-w-xs">
                      <p className="text-sm font-medium text-slate-900 truncate">
                        {humanizeWorkflowName(w.name)}
                      </p>
                      <div className="flex items-center gap-1.5 mt-0.5 min-w-0">
                        <span className="text-xs font-mono text-gray-400 shrink-0">
                          {w.workflow_id.slice(0, 8)}…{w.workflow_id.slice(-4)}
                        </span>
                        {w.input && (
                          <span className="text-xs text-gray-400 truncate">
                            · {extractWorkflowInputArg(w.input)}
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="pr-4 py-3.5 text-xs text-gray-500 whitespace-nowrap text-right">
                      {formatRelativeTime(w.created_at)}
                    </td>
                    <td className="pr-4 py-3.5 text-xs font-mono text-gray-500 text-right whitespace-nowrap">
                      {workflowDuration(w)}
                    </td>
                    <td className="pr-4 py-3.5 text-xs text-gray-500 text-right">
                      {w.step_count}
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
      </div>
    </div>
  )
}
