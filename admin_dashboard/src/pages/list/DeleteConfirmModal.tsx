import { Trash2, Loader2 } from 'lucide-react'

interface Props {
  count: number
  onCancel: () => void
  onConfirm: () => void
  loading?: boolean
}

export function DeleteConfirmModal({ count, onCancel, onConfirm, loading }: Props) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 px-4">
      <div className="w-full max-w-md rounded-xl border border-slate-800 bg-slate-900 shadow-2xl shadow-black/50">
        <div className="flex items-start gap-3 border-b border-slate-800 px-5 py-4">
          <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-red-900/30">
            <Trash2 size={15} className="text-red-400" />
          </div>
          <div>
            <h2 className="text-base font-semibold text-slate-50">Delete workflows?</h2>
            <p className="mt-1 text-sm text-slate-400">
              You&apos;re about to permanently delete{' '}
              <span className="text-slate-200 font-medium">{count} workflow{count !== 1 ? 's' : ''}</span>.
              This action cannot be undone.
            </p>
          </div>
        </div>
        <div className="flex items-center justify-end gap-2 px-5 py-4">
          <button
            type="button"
            onClick={onCancel}
            disabled={loading}
            className="rounded-md border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm font-medium text-slate-200 hover:bg-slate-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={loading}
            className="flex items-center gap-1.5 rounded-md border border-red-700/50 bg-red-900/20 px-3 py-1.5 text-sm font-medium text-red-400 hover:bg-red-900/40 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading && <Loader2 size={13} className="animate-spin" />}
            Delete {count} workflow{count !== 1 ? 's' : ''}
          </button>
        </div>
      </div>
    </div>
  )
}
