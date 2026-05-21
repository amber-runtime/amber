import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { Step, WorkflowStatus } from '../lib/types'
import { extractFinalAnswer } from '../lib/stepHelpers'

interface Props {
  steps: Step[]
  status: WorkflowStatus
}

export function FinalAnswerCard({ steps, status }: Props) {
  const answer = extractFinalAnswer(steps)

  return (
    <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
      <div className="px-5 py-3 border-b border-gray-100 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wider">
          Final Answer
        </h2>
        {status === 'SUCCESS' && answer && (
          <span className="text-xs text-gray-400">Rendered as Markdown</span>
        )}
      </div>

      <div className="px-5 py-4">
        {status === 'PENDING' && !answer && (
          <Skeleton />
        )}
        {status === 'ERROR' && !answer && (
          <p className="text-sm text-red-600">
            Workflow ended in an error before producing a final answer.
          </p>
        )}
        {answer && (
          <div className="prose text-sm text-gray-800 max-w-none">
            <Markdown remarkPlugins={[remarkGfm]}>{answer}</Markdown>
          </div>
        )}
        {!answer && status !== 'PENDING' && status !== 'ERROR' && (
          <p className="text-sm text-gray-400 italic">No final answer found.</p>
        )}
      </div>
    </div>
  )
}

function Skeleton() {
  return (
    <div className="space-y-3 animate-pulse">
      <div className="h-4 bg-gray-200 rounded w-3/4" />
      <div className="h-4 bg-gray-200 rounded w-full" />
      <div className="h-4 bg-gray-200 rounded w-5/6" />
      <div className="h-4 bg-gray-200 rounded w-2/3" />
      <div className="h-4 bg-gray-200 rounded w-full" />
      <p className="text-xs text-amber-600 pt-1 not-italic font-normal">Still running…</p>
    </div>
  )
}
