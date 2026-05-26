import { useSyncExternalStore } from 'react'
import type { ModelPricing } from './types'

let _models: Record<string, ModelPricing> = {}
let _syncedAt: number | null = null
const _listeners = new Set<() => void>()

export function setPricing(
  models: Record<string, ModelPricing>,
  syncedAt: number | null,
): void {
  _models = models
  _syncedAt = syncedAt
  for (const listener of _listeners) listener()
}

export function getPricing(): Record<string, ModelPricing> {
  return _models
}

function subscribe(cb: () => void): () => void {
  _listeners.add(cb)
  return () => {
    _listeners.delete(cb)
  }
}

function getSyncedAtSnapshot(): number | null {
  return _syncedAt
}

export function usePricingSyncedAt(): number | null {
  return useSyncExternalStore(subscribe, getSyncedAtSnapshot)
}
