import { useEffect, useState } from 'react'

interface ToastItem {
  id: string
  message: string
  detail?: string
}

// Module-level subscriber list — lets showToast() work without prop drilling
let subscribers: Array<(t: ToastItem) => void> = []

export function showToast(message: string, detail?: string) {
  const item: ToastItem = { id: crypto.randomUUID(), message, detail }
  subscribers.forEach((fn) => fn(item))
}

export function ToastStack() {
  const [toasts, setToasts] = useState<ToastItem[]>([])

  useEffect(() => {
    const handler = (t: ToastItem) => setToasts((prev) => [...prev, t])
    subscribers.push(handler)
    return () => {
      subscribers = subscribers.filter((s) => s !== handler)
    }
  }, [])

  const dismiss = (id: string) => setToasts((prev) => prev.filter((t) => t.id !== id))

  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 items-end pointer-events-none">
      {toasts.map((t) => (
        <SingleToast key={t.id} toast={t} onDismiss={() => dismiss(t.id)} />
      ))}
    </div>
  )
}

function SingleToast({ toast, onDismiss }: { toast: ToastItem; onDismiss: () => void }) {
  useEffect(() => {
    const timer = setTimeout(onDismiss, 4000)
    return () => clearTimeout(timer)
  }, [onDismiss])

  return (
    <div className="bg-slate-900 border border-slate-800 text-slate-50 rounded-lg px-4 py-3 shadow-lg pointer-events-auto min-w-[260px] max-w-[380px]">
      <p className="text-sm font-medium">{toast.message}</p>
      {toast.detail && (
        <p className="text-xs text-slate-400 mt-0.5 font-mono">{toast.detail}</p>
      )}
    </div>
  )
}
