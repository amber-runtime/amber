import { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react'
import type { ReactNode } from 'react'
import type { WorkflowSummary, WorkflowDetail } from './types'
import { fetchWorkflows } from './api'

const VISIBLE_LIST_POLL_DELAY_MS = 5000

interface WorkflowContextType {
  workflows: WorkflowSummary[]
  workflowDetails: Record<string, WorkflowDetail>
  loading: boolean
  error: string | null
  refresh: () => Promise<void>
  setDetail: (id: string, detail: WorkflowDetail) => void
}

const WorkflowContext = createContext<WorkflowContextType | null>(null)

export function WorkflowProvider({ children }: { children: ReactNode }) {
  const [workflows, setWorkflows] = useState<WorkflowSummary[]>([])
  const [workflowDetails, setWorkflowDetails] = useState<Record<string, WorkflowDetail>>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const loadPromiseRef = useRef<Promise<void> | null>(null)

  const load = useCallback(async () => {
    if (!loadPromiseRef.current) {
      loadPromiseRef.current = (async () => {
        try {
          const data = await fetchWorkflows()
          setWorkflows(data)
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
    await load()
  }, [load])

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
      await load()
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
  }, [load])

  const setDetail = useCallback((id: string, detail: WorkflowDetail) => {
    setWorkflowDetails((prev) => ({ ...prev, [id]: detail }))
  }, [])

  return (
    <WorkflowContext.Provider
      value={{ workflows, workflowDetails, loading, error, refresh, setDetail }}
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
