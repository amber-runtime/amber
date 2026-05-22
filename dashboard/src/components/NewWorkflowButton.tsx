import { Plus } from 'lucide-react'

interface Props {
  onClick: () => void
}

export function NewWorkflowButton({ onClick }: Props) {
  return (
    <button
      onClick={onClick}
      className="flex items-center gap-1.5 bg-amber-500 text-slate-950 font-medium px-3 py-1.5 rounded-md hover:bg-amber-400 transition-colors text-sm"
    >
      <Plus size={14} />
      New Workflow
    </button>
  )
}
