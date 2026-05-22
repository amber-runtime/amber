import { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react'
import type { ReactNode } from 'react'
import type { WorkflowSummary, WorkflowDetail } from './types'
import { fetchWorkflows } from './api'

interface WorkflowContextType {
  workflows: WorkflowSummary[]
  workflowDetails: Record<string, WorkflowDetail>
  loading: boolean
  error: string | null
  refresh: () => Promise<void>
  prependWorkflow: (summary: WorkflowSummary) => void
  setDetail: (id: string, detail: WorkflowDetail) => void
}

const WorkflowContext = createContext<WorkflowContextType | null>(null)

export function WorkflowProvider({ children }: { children: ReactNode }) {
  const [workflows, setWorkflows] = useState<WorkflowSummary[]>([])
  const [workflowDetails, setWorkflowDetails] = useState<Record<string, WorkflowDetail>>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const load = useCallback(async () => {
    try {
      const data = await fetchWorkflows()
      setWorkflows(data)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch workflows')
    } finally {
      setLoading(false)
    }
  }, [])

  const refresh = useCallback(async () => {
    await load()
  }, [load])

  // Schedule polling: 3s if any PENDING, 30s otherwise
  useEffect(() => {
    const scheduleNext = () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
      const hasPending = workflows.some((w) => w.status === 'PENDING')
      const delay = hasPending ? 3000 : 30000
      intervalRef.current = setInterval(() => {
        void load()
      }, delay)
    }
    scheduleNext()
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [workflows, load])

  // Initial fetch on mount
  useEffect(() => {
    void load()
  }, [load])

  const prependWorkflow = useCallback((summary: WorkflowSummary) => {
    setWorkflows((prev) => {
      const exists = prev.some((w) => w.workflow_id === summary.workflow_id)
      if (exists) return prev
      return [summary, ...prev]
    })
  }, [])

  const setDetail = useCallback((id: string, detail: WorkflowDetail) => {
    setWorkflowDetails((prev) => ({ ...prev, [id]: detail }))
  }, [])

  return (
    <WorkflowContext.Provider
      value={{ workflows, workflowDetails, loading, error, refresh, prependWorkflow, setDetail }}
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
