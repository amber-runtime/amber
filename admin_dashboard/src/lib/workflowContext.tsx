import { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react'
import type { ReactNode } from 'react'
import type { WorkflowSummary, WorkflowDetail } from './types'
import { fetchWorkflows } from './api'

const VISIBLE_LIST_POLL_DELAY_MS = 5000
const PAGE_SIZE = 50

interface WorkflowContextType {
  workflows: WorkflowSummary[]
  workflowDetails: Record<string, WorkflowDetail>
  loading: boolean
  loadingMore: boolean
  hasMore: boolean
  error: string | null
  refresh: () => Promise<void>
  loadMore: () => Promise<void>
  setDetail: (id: string, detail: WorkflowDetail) => void
}

const WorkflowContext = createContext<WorkflowContextType | null>(null)

export function WorkflowProvider({ children }: { children: ReactNode }) {
  const [workflows, setWorkflows] = useState<WorkflowSummary[]>([])
  const [workflowDetails, setWorkflowDetails] = useState<Record<string, WorkflowDetail>>({})
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [hasMore, setHasMore] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const loadPromiseRef = useRef<Promise<void> | null>(null)
  const loadedCountRef = useRef<number>(PAGE_SIZE)

  // Re-fetch the currently loaded range from offset 0. Keeps polling refreshes
  // from shrinking the user's loaded view.
  const refreshLoadedRange = useCallback(async () => {
    if (!loadPromiseRef.current) {
      loadPromiseRef.current = (async () => {
        try {
          const page = await fetchWorkflows({ limit: loadedCountRef.current, offset: 0 })
          setWorkflows(page.workflows)
          setHasMore(page.hasMore)
          setError(null)
        } catch (err) {
          setError(err instanceof Error ? err.message : 'Failed to fetch workflows')
        } finally {
          setLoading(false)
          loadPromiseRef.current = null
        }
      })()
    }
    await loadPromiseRef.current
  }, [])

  const refresh = useCallback(async () => {
    await refreshLoadedRange()
  }, [refreshLoadedRange])

  const loadMore = useCallback(async () => {
    if (loadingMore || !hasMore) return
    setLoadingMore(true)
    try {
      const page = await fetchWorkflows({
        limit: PAGE_SIZE,
        offset: loadedCountRef.current,
      })
      setWorkflows((prev) => {
        // Deduplicate by workflow_id in case a new workflow arrived at the top
        // between the last poll and this load-more call.
        const seen = new Set(prev.map((w) => w.workflow_id))
        const additions = page.workflows.filter((w) => !seen.has(w.workflow_id))
        return prev.concat(additions)
      })
      loadedCountRef.current += page.workflows.length
      setHasMore(page.hasMore)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load more workflows')
    } finally {
      setLoadingMore(false)
    }
  }, [hasMore, loadingMore])

  useEffect(() => {
    let cancelled = false

    const clearPollingTimeout = () => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current)
        timeoutRef.current = null
      }
    }

    const scheduleNext = () => {
      clearPollingTimeout()
      if (cancelled || document.hidden) return

      timeoutRef.current = setTimeout(() => {
        void poll()
      }, VISIBLE_LIST_POLL_DELAY_MS)
    }

    const poll = async () => {
      await refreshLoadedRange()
      scheduleNext()
    }

    const handleVisibilityChange = () => {
      if (document.hidden) {
        clearPollingTimeout()
        return
      }
      void poll()
    }

    document.addEventListener('visibilitychange', handleVisibilityChange)
    void poll()

    return () => {
      cancelled = true
      clearPollingTimeout()
      document.removeEventListener('visibilitychange', handleVisibilityChange)
    }
  }, [refreshLoadedRange])

  const setDetail = useCallback((id: string, detail: WorkflowDetail) => {
    setWorkflowDetails((prev) => ({ ...prev, [id]: detail }))
  }, [])

  return (
    <WorkflowContext.Provider
      value={{
        workflows,
        workflowDetails,
        loading,
        loadingMore,
        hasMore,
        error,
        refresh,
        loadMore,
        setDetail,
      }}
    >
      {children}
    </WorkflowContext.Provider>
  )
}

export function useWorkflows(): WorkflowContextType {
  const ctx = useContext(WorkflowContext)
  if (!ctx) throw new Error('useWorkflows must be used inside WorkflowProvider')
  return ctx
}
