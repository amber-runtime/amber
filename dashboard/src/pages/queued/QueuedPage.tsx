import { useState, useEffect, useCallback, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { RefreshCw, AlertCircle, Loader2 } from 'lucide-react'
import { fetchQueuedWorkflows } from '../../lib/api'
import type { QueuedWorkflowSummary } from '../../lib/types'
import { humanizeWorkflowName, formatRelativeTime, shortWorkflowId } from '../../lib/stepHelpers'
import { PageHeader, PAGE_CONTENT_WIDTH_CLASS } from '../../shared/PageHeader'
import { StatusBadge, RetriedPill } from '../../shared/workflowStatus'
import { SearchInput } from '../../shared/SearchInput'

const POLL_DELAY_MS = 5000
const PAGE_SIZE = 50

function matchesSearch(
  w: { name: string; workflow_id: string },
  query: string,
): boolean {
  const q = query.trim().toLowerCase()
  if (q === '') return true
  return w.name.toLowerCase().includes(q) || w.workflow_id.toLowerCase().includes(q)
}

export function QueuedPage() {
  const navigate = useNavigate()
  const [workflows, setWorkflows] = useState<QueuedWorkflowSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [hasMore, setHasMore] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const loadedCountRef = useRef(PAGE_SIZE)
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const fetchPage = useCallback(async () => {
    try {
      const page = await fetchQueuedWorkflows({ limit: loadedCountRef.current, offset: 0 })
      setWorkflows(page.workflows)
      setHasMore(page.hasMore)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch queued workflows')
    } finally {
      setLoading(false)
    }
  }, [])

  const refresh = useCallback(async () => {
    await fetchPage()
  }, [fetchPage])

  const loadMore = useCallback(async () => {
    if (loadingMore || !hasMore) return
    setLoadingMore(true)
    try {
      const page = await fetchQueuedWorkflows({ limit: PAGE_SIZE, offset: loadedCountRef.current })
      setWorkflows((prev) => {
        const seen = new Set(prev.map((w) => w.workflow_id))
        return prev.concat(page.workflows.filter((w) => !seen.has(w.workflow_id)))
      })
      loadedCountRef.current += page.workflows.length
      setHasMore(page.hasMore)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load more')
    } finally {
      setLoadingMore(false)
    }
  }, [hasMore, loadingMore])

  useEffect(() => {
    let cancelled = false

    const schedule = () => {
      timeoutRef.current = setTimeout(() => {
        if (!cancelled) void poll()
      }, POLL_DELAY_MS)
    }

    const poll = async () => {
      await fetchPage()
      if (!cancelled) schedule()
    }

    const handleVisibility = () => {
      if (document.hidden) {
        if (timeoutRef.current) clearTimeout(timeoutRef.current)
      } else {
        void poll()
      }
    }

    document.addEventListener('visibilitychange', handleVisibility)
    void poll()

    return () => {
      cancelled = true
      if (timeoutRef.current) clearTimeout(timeoutRef.current)
      document.removeEventListener('visibilitychange', handleVisibility)
    }
  }, [fetchPage])

  const filtered = workflows.filter((w) => matchesSearch(w, searchQuery))

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

      <div className={`${PAGE_CONTENT_WIDTH_CLASS} px-6 py-5`}>
        <SearchInput
          value={searchQuery}
          onChange={setSearchQuery}
          placeholder="Search by name or ID..."
        />

        {loading && (
          <div className="flex items-center justify-center py-20 gap-3">
            <div className="w-5 h-5 border-2 border-amber-500 border-t-transparent rounded-full animate-spin" />
            <span className="text-sm text-slate-500">Loading queued workflows…</span>
          </div>
        )}

        {!loading && error && (
          <div className="bg-slate-900 border border-red-500/30 rounded-lg px-5 py-6 flex items-start gap-3">
            <AlertCircle size={16} className="text-red-400 shrink-0 mt-0.5" />
            <div className="flex-1 min-w-0">
              <p className="text-sm text-red-400 font-medium mb-1">Failed to load queued workflows</p>
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

        {!loading && !error && (
          <div className="bg-slate-900 border border-slate-800 rounded-lg overflow-hidden">
            {filtered.length === 0 ? (
              <div className="px-4 py-12 text-center text-sm text-slate-500">
                {searchQuery.trim() !== ''
                  ? 'No queued workflows match your search.'
                  : 'No queued workflows.'}
              </div>
            ) : (
              <table className="w-full border-collapse">
                <thead>
                  <tr className="border-b border-slate-800">
                    <th className="px-4 py-2.5 text-left text-xs font-medium text-slate-400 uppercase tracking-wide">
                      Workflow
                    </th>
                    <th className="pr-4 py-2.5 text-right text-xs font-medium text-slate-400 uppercase tracking-wide whitespace-nowrap">
                      Started
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
                  {filtered.map((w) => (
                    <tr
                      key={w.workflow_id}
                      onClick={() => navigate(`/workflows/${w.workflow_id}`)}
                      className="border-b last:border-b-0 border-slate-800 hover:bg-slate-800/50 cursor-pointer transition-colors"
                    >
                      <td className="px-4 py-3.5">
                        <p className="text-sm font-medium text-slate-50">
                          {humanizeWorkflowName(w.name)}
                        </p>
                        <span className="text-xs font-mono text-slate-500">
                          {shortWorkflowId(w.workflow_id)}
                        </span>
                      </td>
                      <td className="pr-4 py-3.5 text-xs text-slate-300 whitespace-nowrap text-right">
                        {w.created_at != null ? formatRelativeTime(w.created_at) : '—'}
                      </td>
                      <td className="pr-4 py-3.5 text-right">
                        <StatusBadge status={w.status} />
                      </td>
                      <td className="pr-4 py-3.5 text-right">
                        <RetriedPill attempts={w.attempts} />
                      </td>
                    </tr>
                  ))}
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
