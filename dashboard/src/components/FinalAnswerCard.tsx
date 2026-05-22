import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { WorkflowStatus } from '../lib/types'

interface Props {
  output: string | null
  status: WorkflowStatus
}

export function FinalAnswerCard({ output, status }: Props) {
  if (status !== 'SUCCESS' || output == null) return null

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-lg overflow-hidden">
      <div className="px-5 py-3 border-b border-slate-800 flex items-center justify-between">
        <h2 className="text-xs font-medium text-slate-400 uppercase tracking-wider">
          Final Answer
        </h2>
        <span className="text-xs text-slate-500">Rendered as Markdown</span>
      </div>
      <div className="px-5 py-4">
        <div className="prose text-sm text-slate-300 max-w-none">
          <Markdown remarkPlugins={[remarkGfm]}>{output}</Markdown>
        </div>
      </div>
    </div>
  )
}
