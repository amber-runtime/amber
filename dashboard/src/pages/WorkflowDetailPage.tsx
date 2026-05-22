import { useEffect, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft, RefreshCw } from 'lucide-react'
import { useWorkflows } from '../lib/workflowContext'
import { fetchWorkflowDetail } from '../lib/api'
import { WorkflowHeader } from '../components/WorkflowHeader'
import { FinalAnswerCard } from '../components/FinalAnswerCard'
import { StepTimeline } from '../components/StepTimeline'

export function WorkflowDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { workflowDetails, setDetail } = useWorkflows()
  const data = id ? workflowDetails[id] : null
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const load = async () => {
    if (!id) return
    try {
      const detail = await fetchWorkflowDetail(id)
      setDetail(id, detail)
    } catch {
      // keep stale data on error
    }
  }

  useEffect(() => {
    void load()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id])

  // Poll every 2s while PENDING, stop when terminal
  useEffect(() => {
    if (pollingRef.current) clearInterval(pollingRef.current)
    if (!data || data.workflow.status === 'PENDING') {
      pollingRef.current = setInterval(() => {
        void load()
      }, 2000)
    }
    return () => {
      if (pollingRef.current) clearInterval(pollingRef.current)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data?.workflow.status, id])

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
          <div className="w-5 h-5 border-2 border-amber-500 border-t-transparent rounded-full animate-spin" />
          <p className="text-sm text-slate-500">Loading workflow…</p>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-slate-950">
      <BackNav />

      <WorkflowHeader workflow={data.workflow} steps={data.steps} />

      <main className="max-w-4xl mx-auto px-6 py-6 space-y-4">
        {/* TODO: input surfacing is pending a backend fix — topic card hidden until available */}

        <FinalAnswerCard output={data.workflow.output} status={data.workflow.status} />

        {data.workflow.status === 'PENDING' && data.steps.length === 0 && (
          <div className="bg-slate-900 border border-slate-800 rounded-lg px-5 py-8 text-center">
            <div className="flex items-center justify-center gap-2 text-amber-400 mb-2">
              <div className="w-4 h-4 border-2 border-amber-400 border-t-transparent rounded-full animate-spin" />
              <span className="text-sm">Waiting for first step…</span>
            </div>
            <p className="text-xs text-slate-500">Polling every 2 seconds</p>
          </div>
        )}

        {data.steps.length > 0 && (
          <StepTimeline workflow={data.workflow} steps={data.steps} />
        )}
      </main>

      {data.workflow.status === 'PENDING' && (
        <div className="fixed bottom-4 right-4">
          <button
            onClick={() => void load()}
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
