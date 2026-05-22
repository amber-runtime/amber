import { useEffect, useState } from 'react'
import { X, Loader2, AlertCircle } from 'lucide-react'
import type { Agent } from '../lib/types'
import { fetchAgents } from '../lib/api'

interface Props {
  onClose: () => void
  onSubmit: (agent: string, input: string, crashDemo: boolean) => Promise<void>
}

export function NewWorkflowModal({ onClose, onSubmit }: Props) {
  const [agents, setAgents] = useState<Agent[]>([])
  const [agentsLoading, setAgentsLoading] = useState(true)
  const [agentsError, setAgentsError] = useState<string | null>(null)

  const [selectedAgent, setSelectedAgent] = useState('')
  const [input, setInput] = useState('')
  const [crashDemo, setCrashDemo] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)

  // Fetch agents on open
  useEffect(() => {
    fetchAgents()
      .then((data) => {
        setAgents(data)
        if (data.length > 0) setSelectedAgent(data[0].name)
      })
      .catch((err) => setAgentsError(err instanceof Error ? err.message : 'Failed to load agents'))
      .finally(() => setAgentsLoading(false))
  }, [])

  // Reset crash demo when agent changes away from travel-concierge
  useEffect(() => {
    if (selectedAgent !== 'travel-concierge') setCrashDemo(false)
  }, [selectedAgent])

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [onClose])

  const canSubmit = !agentsLoading && !agentsError && selectedAgent && input.trim() && !submitting

  const handleSubmit = async () => {
    if (!canSubmit) return
    setSubmitting(true)
    setSubmitError(null)
    try {
      await onSubmit(selectedAgent, input.trim(), crashDemo)
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : 'Failed to start workflow')
      setSubmitting(false)
    }
  }

  const isTravelConcierge = selectedAgent === 'travel-concierge'

  return (
    <div
      className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div className="bg-slate-900 border border-slate-700 rounded-lg p-6 w-full max-w-[480px] shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-base font-semibold text-slate-50">New Workflow</h2>
          <button
            onClick={onClose}
            className="p-1 rounded hover:bg-slate-800 text-slate-500 hover:text-slate-300 transition-colors"
          >
            <X size={16} />
          </button>
        </div>

        {/* Agent dropdown */}
        <div className="mb-4">
          <label className="block text-sm text-slate-400 mb-1.5">Agent</label>
          {agentsLoading ? (
            <div className="flex items-center gap-2 text-sm text-slate-500 py-2">
              <Loader2 size={14} className="animate-spin" />
              Loading agents…
            </div>
          ) : agentsError ? (
            <div className="flex items-center gap-2 text-sm text-red-400 py-2">
              <AlertCircle size={14} />
              {agentsError}
            </div>
          ) : (
            <select
              value={selectedAgent}
              onChange={(e) => {
                setSelectedAgent(e.target.value)
                setInput('')
              }}
              className="w-full bg-slate-800 border border-slate-700 rounded-md px-3 py-2 text-sm text-slate-200 focus:outline-none focus:ring-1 focus:ring-amber-500/50 focus:border-amber-500/50 cursor-pointer"
            >
              {agents.map((a) => (
                <option key={a.name} value={a.name}>
                  {a.name
                    .split('-')
                    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
                    .join(' ')}
                </option>
              ))}
            </select>
          )}
        </div>

        {/* Input field */}
        <div className="mb-4">
          <label className="block text-sm text-slate-400 mb-1.5">Input</label>
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') void handleSubmit()
            }}
            placeholder="e.g. vector database comparison 2026"
            autoFocus
            className="w-full bg-slate-800 border border-slate-700 rounded-md px-3 py-2 text-sm text-slate-200 placeholder:text-slate-500 focus:outline-none focus:ring-1 focus:ring-amber-500/50 focus:border-amber-500/50"
          />
        </div>

        {/* Crash demo checkbox */}
        <div className="mb-5">
          <label
            className={`flex items-start gap-2.5 cursor-pointer ${
              !isTravelConcierge ? 'opacity-40 cursor-not-allowed' : ''
            }`}
          >
            <input
              type="checkbox"
              checked={crashDemo}
              disabled={!isTravelConcierge}
              onChange={(e) => setCrashDemo(e.target.checked)}
              className="mt-0.5 accent-amber-500"
            />
            <span className="text-sm text-slate-300">
              Demo: crash during hotel lookup (travel-concierge only)
            </span>
          </label>
          {isTravelConcierge && (
            <p className="mt-1.5 ml-[22px] text-xs text-slate-500 leading-relaxed">
              Workflow will crash once during hotel lookup, then auto-recover. Use this to demonstrate durability.
            </p>
          )}
        </div>

        {/* Submit error */}
        {submitError && (
          <div className="mb-4 flex items-start gap-2 text-sm text-red-400">
            <AlertCircle size={14} className="shrink-0 mt-0.5" />
            {submitError}
          </div>
        )}

        {/* Actions */}
        <div className="flex items-center justify-end gap-2">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm text-slate-400 hover:text-slate-200 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={() => void handleSubmit()}
            disabled={!canSubmit}
            className="px-4 py-2 text-sm bg-amber-500 text-slate-950 font-medium rounded-md hover:bg-amber-400 disabled:opacity-40 disabled:cursor-not-allowed transition-colors flex items-center gap-1.5"
          >
            {submitting && <Loader2 size={13} className="animate-spin" />}
            Run
          </button>
        </div>
      </div>
    </div>
  )
}
