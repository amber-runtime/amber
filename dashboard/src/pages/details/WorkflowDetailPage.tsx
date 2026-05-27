import { useCallback, useEffect, useRef, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { AlertCircle, ArrowLeft, RefreshCw } from 'lucide-react'
import { useWorkflows } from '../../lib/workflowContext'
import { fetchWorkflowDetail } from '../../lib/api'
import type { SelectedStepId } from '../../lib/types'
import { WorkflowHeader } from './components/WorkflowHeader'
import { StepList } from './components/StepList'
import { StepDetailPanel } from './components/right/StepDetailPanel'
import { WorkflowDefaultPanel } from './components/right/WorkflowDefaultPanel'

const DETAIL_POLL_DELAY_MS = 2000

// Workflows in these statuses won't tick again, so we stop polling. Includes
// MAX_RECOVERY_ATTEMPTS_EXCEEDED, which isn't in the WorkflowStatus union yet
// but can appear in raw backend payloads.
const TERMINAL_STATUSES: ReadonlySet<string> = new Set([
  'SUCCESS',
  'ERROR',
  'CANCELLED',
  'MAX_RECOVERY_ATTEMPTS_EXCEEDED',
])

export function WorkflowDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { workflowDetails, setDetail } = useWorkflows()
  const data = id ? workflowDetails[id] : null
  const [selectedStepId, setSelectedStepId] = useState<SelectedStepId>(null)
  const [fetchError, setFetchError] = useState<string | null>(null)
  const loadPromiseRef = useRef<Promise<void> | null>(null)
  const loadWorkflowIdRef = useRef<string | null>(null)

  const handleStepClick = (stepId: number) => {
    setSelectedStepId((prev) => (prev === stepId ? null : stepId))
  }

  const loadDetail = useCallback(async (): Promise<void> => {
    if (!id) return
    if (loadPromiseRef.current && loadWorkflowIdRef.current === id) {
      await loadPromiseRef.current
      return
    }
    const workflowId = id
    loadWorkflowIdRef.current = workflowId
    let promise!: Promise<void>
    promise = (async () => {
      try {
        const detail = await fetchWorkflowDetail(workflowId)
        setDetail(workflowId, detail)
        setFetchError(null)
      } catch (err) {
        setFetchError(err instanceof Error ? err.message : 'Refresh failed')
      } finally {
        if (loadPromiseRef.current === promise) {
          loadPromiseRef.current = null
          loadWorkflowIdRef.current = null
        }
      }
    })()
    loadPromiseRef.current = promise
    await promise
  }, [id, setDetail])

  // Mount-time fetch (and refetch when id changes).
  useEffect(() => {
    void loadDetail()
  }, [loadDetail])

  // Poll while the workflow isn't in a terminal state. When the status flips
  // to terminal (or to non-terminal after a Resume), the dependency change
  // tears down the old interval and starts a new one if needed.
  const status = data?.workflow.status
  useEffect(() => {
    if (!status || TERMINAL_STATUSES.has(status)) return
    const interval = setInterval(() => {
      void loadDetail()
    }, DETAIL_POLL_DELAY_MS)
    return () => clearInterval(interval)
  }, [status, loadDetail])

  const BackNav = () => (
    <div className="bg-slate-900 border-b border-slate-800 px-6 py-2">
      <button
        onClick={() => navigate(-1)}
        className="flex items-center gap-1.5 text-sm text-slate-400 hover:text-slate-200 transition-colors"
      >
        <ArrowLeft size={14} />
        Workflows
      </button>
    </div>
  )

  if (!data) {
    return (
      <div className="min-h-screen bg-slate-950">
        <BackNav />
        <div className="flex flex-col items-center justify-center py-32 gap-4">
          {fetchError ? (
            <>
              <AlertCircle size={20} className="text-amber-400" />
              <p className="text-sm text-amber-200">Failed to load workflow.</p>
              <p className="text-xs text-slate-500 max-w-md text-center break-all">
                {fetchError}
              </p>
              <button
                onClick={() => void loadDetail()}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-slate-800 border border-slate-700 text-slate-300 rounded-md hover:bg-slate-700 transition-colors"
              >
                <RefreshCw size={12} />
                Retry
              </button>
            </>
          ) : (
            <>
              <div className="w-5 h-5 border-2 border-amber-500 border-t-transparent rounded-full animate-spin" />
              <p className="text-sm text-slate-500">Loading workflow…</p>
            </>
          )}
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-slate-950">
      <BackNav />

      {fetchError && (
        <div className="bg-amber-500/10 border-b border-amber-500/30 px-6 py-2 flex items-center gap-2">
          <AlertCircle size={14} className="text-amber-400 shrink-0" />
          <span className="text-xs text-amber-200 flex-1">
            Failed to refresh. Showing last known data.
          </span>
          <span className="text-[11px] text-amber-300/60 font-mono truncate max-w-[40%]">
            {fetchError}
          </span>
        </div>
      )}

      <WorkflowHeader
        workflow={data.workflow}
        steps={data.steps}
        onActionSuccess={loadDetail}
      />

      <main className="max-w-7xl mx-auto px-6 py-6">
        {(() => {
          const selectedStep =
            selectedStepId != null
              ? data.steps.find((s) => s.step_id === selectedStepId) ?? null
              : null

          return (
            <div className="grid grid-cols-5 gap-4 items-start">
              <div className="col-span-3 min-w-0">
                {data.steps.length === 0 ? (
                  <div className="bg-slate-900 border border-slate-800 rounded-lg px-5 py-8 text-center">
                    <div className="flex items-center justify-center gap-2 text-amber-400 mb-2">
                      <div className="w-4 h-4 border-2 border-amber-400 border-t-transparent rounded-full animate-spin" />
                      <span className="text-sm">Waiting for first step…</span>
                    </div>
                    <p className="text-xs text-slate-500">Polling every 2 seconds</p>
                  </div>
                ) : (
                  <StepList
                    workflow={data.workflow}
                    steps={data.steps}
                    selectedStepId={selectedStepId}
                    onStepClick={handleStepClick}
                  />
                )}
              </div>
              <aside className="col-span-2 sticky top-0 h-screen overflow-y-auto bg-slate-900 border border-slate-800 rounded-lg">
                {selectedStep != null ? (
                  <StepDetailPanel step={selectedStep} />
                ) : (
                  <WorkflowDefaultPanel workflow={data.workflow} steps={data.steps} />
                )}
              </aside>
            </div>
          )
        })()}
      </main>

      {data.workflow.status === 'PENDING' && (
        <div className="fixed bottom-4 right-4">
          <button
            onClick={() => void loadDetail()}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-slate-800 border border-slate-700 text-slate-300 rounded-full hover:bg-slate-700 transition-colors"
          >
            <RefreshCw size={12} />
            Refresh now
          </button>
        </div>
      )}
    </div>
  )
}
