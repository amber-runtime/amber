import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { RefreshCw, CheckCircle2, XCircle, AlertCircle, Loader2 } from 'lucide-react'
import type { WorkflowSummary, WorkflowStatus } from '../../lib/types'
import { useWorkflows } from '../../lib/workflowContext'
import {
  humanizeWorkflowName,
  formatRelativeTime,
  formatDuration,
  shortWorkflowId,
  deriveWorkflowDisplayStatus,
} from '../../lib/stepHelpers'
import { PageHeader } from '../../shared/PageHeader'
import { StatusBadge, RetriedPill } from '../../shared/workflowStatus'
import { SearchInput } from '../../shared/SearchInput'

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

type DateFilter = 'all' | '24h' | '7d' | '30d'

const DATE_LABELS: Record<DateFilter, string> = {
  all: 'All time',
  '24h': 'Last 24h',
  '7d': 'Last 7d',
  '30d': 'Last 30d',
}

const DATE_FILTER_MS: Record<DateFilter, number | null> = {
  all: null,
  '24h': 24 * 60 * 60 * 1000,
  '7d': 7 * 24 * 60 * 60 * 1000,
  '30d': 30 * 24 * 60 * 60 * 1000,
}

function matchesSearch(
  w: { name: string; workflow_id: string },
  query: string,
): boolean {
  const q = query.trim().toLowerCase()
  if (q === '') return true
  return w.name.toLowerCase().includes(q) || w.workflow_id.toLowerCase().includes(q)
}

function matchesDate(createdAt: number, dateFilter: DateFilter): boolean {
  const window = DATE_FILTER_MS[dateFilter]
  return window === null || Date.now() - createdAt <= window
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
  if (status === 'ENQUEUED')
    return (
      <span className="relative flex h-3 w-3 shrink-0 mt-0.5">
        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75" />
        <span className="relative inline-flex rounded-full h-3 w-3 bg-blue-500" />
      </span>
    )
  return <span className="w-3.5 h-3.5 rounded-full bg-slate-600 shrink-0" />
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
  const { workflows, workflowDetails, loading, loadingMore, hasMore, error, refresh, loadMore } = useWorkflows()
  const [filter, setFilter] = useState<Filter>('all')
  const [dateFilter, setDateFilter] = useState<DateFilter>('all')
  const [searchQuery, setSearchQuery] = useState('')
  const [now, setNow] = useState(Date.now())
  const displayStatusByWorkflowId = new Map(
    workflows.map((workflow) => [
      workflow.workflow_id,
      deriveWorkflowDisplayStatus(
        workflow,
        workflowDetails[workflow.workflow_id]?.steps ?? [],
      ),
    ]),
  )

  // Tick every second when any workflow is PENDING so durations update live
  useEffect(() => {
    const hasPending = workflows.some((w) => w.status === 'PENDING')
    if (!hasPending) return
    const timer = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(timer)
  }, [workflows])

  // Apply search + date first so chip counts reflect what's actually
  // selectable; the status chip itself is applied on top of this set.
  const preStatusFiltered = workflows.filter(
    (w) => matchesDate(w.created_at, dateFilter) && matchesSearch(w, searchQuery),
  )

  const counts = {
    all: preStatusFiltered.length,
    completed: preStatusFiltered.filter((w) => displayStatusByWorkflowId.get(w.workflow_id) === 'SUCCESS').length,
    running: preStatusFiltered.filter((w) => displayStatusByWorkflowId.get(w.workflow_id) === 'PENDING').length,
    errored: preStatusFiltered.filter((w) => displayStatusByWorkflowId.get(w.workflow_id) === 'ERROR').length,
  }

  const FILTER_LABELS: Record<Filter, string> = {
    all: `All (${counts.all})`,
    completed: `Completed (${counts.completed})`,
    running: `Pending (${counts.running})`,
    errored: `Errored (${counts.errored})`,
  }

  const filtered = preStatusFiltered.filter((w) => {
    const target = FILTER_STATUS[filter]
    return target === null || displayStatusByWorkflowId.get(w.workflow_id) === target
  })

  return (
    <div className="min-h-screen bg-slate-950">
      <PageHeader
        actions={
          <button
            onClick={() => void refresh()}
            className="p-2 rounded-md hover:bg-slate-800 text-slate-400 hover:text-slate-200 transition-colors"
            title="Refresh"
          >
            <RefreshCw size={16} />
          </button>
        }
      />

      <div className="max-w-5xl mx-auto px-6 py-5">
        <SearchInput
          value={searchQuery}
          onChange={setSearchQuery}
          placeholder="Search by name or ID..."
        />

        {/* Status filter chips */}
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

        {/* Date filter chips */}
        <div className="flex items-center gap-2 mb-4 flex-wrap">
          {(Object.keys(DATE_LABELS) as DateFilter[]).map((d) => (
            <button
              key={d}
              onClick={() => setDateFilter(d)}
              className={`px-3 py-1.5 rounded-full text-xs font-medium transition-colors ${
                dateFilter === d
                  ? 'bg-amber-500 text-slate-950 font-medium'
                  : 'bg-slate-900 text-slate-300 border border-slate-800 hover:bg-slate-800'
              }`}
            >
              {DATE_LABELS[d]}
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
                <p>
                  {searchQuery.trim() !== '' || dateFilter !== 'all'
                    ? 'No workflows match your filters.'
                    : EMPTY_MESSAGES[filter]}
                </p>
                {hasMore &&
                  filter !== 'all' &&
                  searchQuery.trim() === '' &&
                  dateFilter === 'all' && (
                    <p className="mt-1 text-xs text-slate-600">
                      Older workflows haven&rsquo;t been loaded — try Load more below.
                    </p>
                  )}
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
                      Status
                    </th>
                    <th className="pr-4 py-2.5 text-right text-xs font-medium text-slate-400 uppercase tracking-wide">
                      Retried
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((w) => {
                    const displayStatus = displayStatusByWorkflowId.get(w.workflow_id) ?? w.status
                    return (
                      <tr
                        key={w.workflow_id}
                        onClick={() => navigate(`/workflows/${w.workflow_id}`)}
                        className="border-b last:border-b-0 border-slate-800 hover:bg-slate-800/50 cursor-pointer transition-colors"
                      >
                        <td className="pl-4 pr-2 py-3.5">
                          <StatusIcon status={displayStatus} />
                        </td>
                        <td className="pr-4 py-3.5 max-w-xs">
                          <p className="text-sm font-medium text-slate-50 truncate">
                            {humanizeWorkflowName(w.name)}
                          </p>
                          <span className="text-xs font-mono text-slate-500">
                            {shortWorkflowId(w.workflow_id)}
                          </span>
                        </td>
                        <td className="pr-4 py-3.5 text-xs text-slate-300 whitespace-nowrap text-right">
                          {formatRelativeTime(w.created_at)}
                        </td>
                        <td className="pr-4 py-3.5 text-xs font-mono text-slate-300 text-right whitespace-nowrap">
                          {workflowDuration(w, now)}
                        </td>
                        <td className="pr-4 py-3.5 text-right">
                          <StatusBadge status={displayStatus} />
                        </td>
                        <td className="pr-4 py-3.5 text-right">
                          <RetriedPill attempts={w.attempts} />
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            )}

            {hasMore && (
              <button
                type="button"
                onClick={() => void loadMore()}
                disabled={loadingMore}
                className="w-full px-4 py-3 border-t border-slate-800 text-sm text-slate-300 hover:bg-slate-800/50 disabled:text-slate-600 disabled:hover:bg-transparent disabled:cursor-not-allowed transition-colors flex items-center justify-center gap-2"
              >
                {loadingMore && <Loader2 size={13} className="animate-spin" />}
                {loadingMore ? 'Loading…' : 'Load more'}
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
