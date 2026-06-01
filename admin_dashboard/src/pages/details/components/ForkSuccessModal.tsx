import { X } from 'lucide-react'

interface Props {
  workflowId: string
  onClose: () => void
  onViewWorkflow: (workflowId: string) => void
}

export function ForkSuccessModal({ workflowId, onClose, onViewWorkflow }: Props) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 px-4">
      <div className="w-full max-w-md rounded-xl border border-slate-800 bg-slate-900 shadow-2xl shadow-black/50">
        <div className="flex items-start justify-between gap-4 border-b border-slate-800 px-5 py-4">
          <div>
            <h2 className="text-base font-semibold text-slate-50">Workflow forked</h2>
            <p className="mt-1 text-sm text-slate-400">
              A new workflow was created from this step and is now running. This
              workflow was not changed.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-1 text-slate-500 hover:bg-slate-800 hover:text-slate-300 transition-colors"
            aria-label="Close"
          >
            <X size={16} />
          </button>
        </div>
        <div className="px-5 py-4">
          <p className="text-[11px] uppercase tracking-wider text-slate-500">New workflow ID</p>
          <p className="mt-2 break-all font-mono text-sm text-slate-200">{workflowId}</p>
        </div>
        <div className="flex items-center justify-end gap-2 border-t border-slate-800 px-5 py-4">
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm font-medium text-slate-200 hover:bg-slate-700 transition-colors"
          >
            Stay here
          </button>
          <button
            type="button"
            onClick={() => onViewWorkflow(workflowId)}
            className="rounded-md border border-emerald-700 bg-emerald-600/20 px-3 py-1.5 text-sm font-medium text-emerald-200 hover:bg-emerald-600/30 transition-colors"
          >
            View forked workflow
          </button>
        </div>
      </div>
    </div>
  )
}
