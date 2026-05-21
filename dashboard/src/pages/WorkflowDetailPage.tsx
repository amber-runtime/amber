import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'
import type { WorkflowDetail } from '../lib/types'
import {
  mockWorkflowSuccess,
  mockWorkflowPending,
  mockWorkflowError,
} from '../lib/mockData'
import { WorkflowHeader } from '../components/WorkflowHeader'
import { InputCard } from '../components/InputCard'
import { FinalAnswerCard } from '../components/FinalAnswerCard'
import { StepTimeline } from '../components/StepTimeline'

const FIXTURES: Record<string, WorkflowDetail> = {
  '019e3c95-08de-7451-af78-01a1f83c43bb': mockWorkflowSuccess,
  '019e3ca1-3f22-7b90-bc34-9d5e2c7f1a44': mockWorkflowPending,
  '019e3cb3-9a14-7c65-dd21-3b8f4e0d2c55': mockWorkflowError,
}

const FIXTURE_LABELS: [string, string][] = [
  ['019e3c95-08de-7451-af78-01a1f83c43bb', 'SUCCESS'],
  ['019e3ca1-3f22-7b90-bc34-9d5e2c7f1a44', 'PENDING'],
  ['019e3cb3-9a14-7c65-dd21-3b8f4e0d2c55', 'ERROR'],
]

export function WorkflowDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const data = id ? FIXTURES[id] : null

  if (!data) {
    return (
      <div className="min-h-screen bg-gray-50">
        <div className="bg-white border-b border-gray-200 px-6 py-2">
          <button
            onClick={() => navigate(-1)}
            className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-slate-900 transition-colors"
          >
            <ArrowLeft size={14} />
            Workflows
          </button>
        </div>
        <div className="flex flex-col items-center justify-center py-32 gap-4">
          <p className="text-sm text-gray-400">
            No detail data available for workflow{' '}
            <span className="font-mono text-gray-600">{id ?? '(unknown)'}</span>.
          </p>
          <button
            onClick={() => navigate('/')}
            className="text-sm text-slate-600 hover:text-slate-900 flex items-center gap-1.5 transition-colors"
          >
            <ArrowLeft size={14} />
            Back to workflows
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Back nav */}
      <div className="bg-white border-b border-gray-200 px-6 py-2">
        <button
          onClick={() => navigate(-1)}
          className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-slate-900 transition-colors"
        >
          <ArrowLeft size={14} />
          Workflows
        </button>
      </div>

      <WorkflowHeader workflow={data.workflow} steps={data.steps} />

      <main className="max-w-4xl mx-auto px-6 py-6 space-y-4">
        <InputCard input={data.workflow.input} />
        <FinalAnswerCard steps={data.steps} status={data.workflow.status} />
        <StepTimeline workflow={data.workflow} steps={data.steps} />
      </main>

      {/* Dev fixture switcher */}
      <div className="fixed bottom-4 right-4 z-50">
        <div className="bg-white border border-gray-200 rounded-lg shadow-lg px-3 py-2.5 flex items-center gap-2">
          <span className="text-xs text-gray-400 font-medium">Fixture</span>
          <select
            value={id ?? ''}
            onChange={(e) => navigate(`/workflows/${e.target.value}`)}
            className="text-xs border border-gray-200 rounded px-2 py-1 bg-white text-gray-700 focus:outline-none focus:ring-1 focus:ring-slate-300 cursor-pointer"
          >
            {FIXTURE_LABELS.map(([fid, label]) => (
              <option key={fid} value={fid}>
                {label}
              </option>
            ))}
          </select>
        </div>
      </div>
    </div>
  )
}
