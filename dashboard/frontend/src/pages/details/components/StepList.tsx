import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type {
  Step,
  SelectedStepId,
  AgentGroup,
  WorkflowInfo,
  WorkflowStatus,
} from '../../../lib/types'
import type { DowntimeInterval } from '../../../lib/stepHelpers'
import {
  buildTimelineSteps,
  computeWorkflowWindow,
  deriveVisualActiveStepId,
  filterStepsBySearch,
  groupStepsByAgent,
  isWorkflowActivelyRunning,
} from '../../../lib/stepHelpers'
import { AgentGroupSection } from './AgentGroupSection'
import { StepListToolbar } from './StepListToolbar'
import { TimeAxis } from './TimeAxis'

interface Props {
  workflow: WorkflowInfo
  steps: Step[]
  displayStatus?: WorkflowStatus
  activeRefreshDowntimeStart?: number | null
  resolvedRefreshDowntimes?: DowntimeInterval[]
  selectedStepId: SelectedStepId
  onStepClick: (id: number) => void
}

const PREFLIGHT_KEY = '__preflight__'

function groupKey(group: AgentGroup): string {
  return group.agentName ?? PREFLIGHT_KEY
}

function stepRowKey(step: Step, groupIndex: number, stepIndex: number): string {
  return step.step_id != null
    ? `step-${step.step_id}`
    : `fallback-${groupIndex}-${stepIndex}`
}

export function StepList({
  workflow,
  steps,
  displayStatus,
  activeRefreshDowntimeStart = null,
  resolvedRefreshDowntimes = [],
  selectedStepId,
  onStepClick,
}: Props) {
  const timelineSteps = useMemo(() => buildTimelineSteps(workflow, steps), [workflow, steps])
  const groups = useMemo(() => groupStepsByAgent(timelineSteps), [timelineSteps])
  const [nowMs, setNowMs] = useState(() => Date.now())
  const refreshAnchorByStartRef = useRef(new Map<number, string>())

  const effectiveStatus = displayStatus ?? workflow.status
  const [searchQuery, setSearchQuery] = useState('')
  const [expansion, setExpansion] = useState<Map<string, boolean>>(() => {
    const m = new Map<string, boolean>()
    for (const g of groups) m.set(groupKey(g), true)
    return m
  })

  // Add expansion entries for groups that appear later (e.g. during polling).
  useEffect(() => {
    setExpansion((prev) => {
      const seen = new Set<string>()
      let changed = false
      const next = new Map(prev)
      for (const g of groups) {
        const k = groupKey(g)
        seen.add(k)
        if (!next.has(k)) {
          next.set(k, true)
          changed = true
        }
      }
      return changed ? next : prev
    })
  }, [groups])

  const matchingStepIds = useMemo(
    () => filterStepsBySearch(timelineSteps, searchQuery),
    [timelineSteps, searchQuery],
  )
  const searching = searchQuery.trim() !== ''

  // During search: filter steps inside groups and drop empty groups.
  // When not searching: pass groups through unchanged.
  const renderedGroups: AgentGroup[] = useMemo(() => {
    if (!searching) return groups
    return groups
      .map((g) => ({
        ...g,
        steps: g.steps.filter(
          (s) => s.step_id != null && matchingStepIds.has(s.step_id),
        ),
      }))
      .filter((g) => g.steps.length > 0)
  }, [groups, searching, matchingStepIds])

  const lastVisibleStepKey = useMemo(() => {
    for (let groupIndex = renderedGroups.length - 1; groupIndex >= 0; groupIndex--) {
      const group = renderedGroups[groupIndex]
      const key = groupKey(group)
      const effectiveExpanded = searching ? true : expansion.get(key) ?? true
      if (!effectiveExpanded) continue
      for (let stepIndex = group.steps.length - 1; stepIndex >= 0; stepIndex--) {
        return stepRowKey(group.steps[stepIndex], groupIndex, stepIndex)
      }
    }
    return null
  }, [renderedGroups, searching, expansion])

  useEffect(() => {
    if (activeRefreshDowntimeStart == null || lastVisibleStepKey == null) return
    const anchors = refreshAnchorByStartRef.current
    if (!anchors.has(activeRefreshDowntimeStart)) {
      anchors.set(activeRefreshDowntimeStart, lastVisibleStepKey)
    }
  }, [activeRefreshDowntimeStart, lastVisibleStepKey])

  const derivedDowntimeIntervals = useMemo(() => {
    const intervals: DowntimeInterval[] = []
    intervals.push(
      ...resolvedRefreshDowntimes.map((interval) => ({
        ...interval,
        anchorRowKey:
          interval.anchorRowKey ??
          refreshAnchorByStartRef.current.get(interval.start),
      })),
    )
    if (activeRefreshDowntimeStart != null) {
      intervals.push({
        start: activeRefreshDowntimeStart,
        end: null,
        source: 'refresh',
        anchorRowKey:
          refreshAnchorByStartRef.current.get(activeRefreshDowntimeStart) ??
          lastVisibleStepKey ??
          undefined,
      })
    }
    return intervals
  }, [
    resolvedRefreshDowntimes,
    activeRefreshDowntimeStart,
    lastVisibleStepKey,
  ])

  const hasActiveDowntime = derivedDowntimeIntervals.some((interval) => interval.end == null)
  const shouldTickTimeline =
    hasActiveDowntime || isWorkflowActivelyRunning(effectiveStatus)

  useEffect(() => {
    if (!shouldTickTimeline) return
    setNowMs(Date.now())
    const interval = setInterval(() => setNowMs(Date.now()), 1000)
    return () => clearInterval(interval)
  }, [shouldTickTimeline])

  const window = useMemo(
    () => computeWorkflowWindow(
      { ...workflow, status: effectiveStatus },
      timelineSteps,
      hasActiveDowntime ? nowMs : null,
    ),
    [workflow, effectiveStatus, timelineSteps, hasActiveDowntime, nowMs],
  )
  const workflowIsActive =
    !hasActiveDowntime && isWorkflowActivelyRunning(effectiveStatus)
  const visualActiveStepId = useMemo(
    () => deriveVisualActiveStepId(effectiveStatus, timelineSteps),
    [effectiveStatus, timelineSteps],
  )

  const handleExpandAll = useCallback(() => {
    setExpansion(() => {
      const m = new Map<string, boolean>()
      for (const g of groups) m.set(groupKey(g), true)
      return m
    })
  }, [groups])

  const handleCollapseAll = useCallback(() => {
    setExpansion(() => {
      const m = new Map<string, boolean>()
      for (const g of groups) m.set(groupKey(g), false)
      return m
    })
  }, [groups])

  const handleGroupExpandChange = useCallback(
    (key: string, expanded: boolean) => {
      setExpansion((prev) => {
        const next = new Map(prev)
        next.set(key, expanded)
        return next
      })
    },
    [],
  )

  if (steps.length === 0) {
    return (
      <div className="bg-slate-900 border border-slate-800 rounded-lg px-5 py-8 text-center">
        <p className="text-sm text-slate-500">No steps recorded yet.</p>
      </div>
    )
  }

  return (
    <div>
      <StepListToolbar
        searchQuery={searchQuery}
        onSearchChange={setSearchQuery}
        onExpandAll={handleExpandAll}
        onCollapseAll={handleCollapseAll}
      />

      {timelineSteps.length > 1 && <TimeAxis start={window.start} end={window.end} />}

      {renderedGroups.length === 0 ? (
        <div className="bg-slate-900 border border-slate-800 rounded-lg px-5 py-8 text-center">
          <p className="text-sm text-slate-500">
            No steps match &ldquo;{searchQuery}&rdquo;
          </p>
        </div>
      ) : (
        <div className="relative space-y-2">
          {renderedGroups.map((group, i) => {
            const key = groupKey(group)
            // During search, force expansion so matches are visible without
            // permanently clobbering the user's preferred state.
            const effectiveExpanded = searching ? true : expansion.get(key) ?? true
            return (
              <AgentGroupSection
                key={`${key}-${i}`}
                group={group}
                selectedStepId={selectedStepId}
                onStepClick={onStepClick}
                isExpanded={effectiveExpanded}
                onExpandChange={(exp) => handleGroupExpandChange(key, exp)}
                workflowStart={window.start}
                workflowEnd={window.end}
                workflowIsActive={workflowIsActive}
                visualActiveStepId={visualActiveStepId}
                downtimeIntervals={derivedDowntimeIntervals}
                groupIndex={i}
                nowMs={nowMs}
              />
            )
          })}
        </div>
      )}
    </div>
  )
}
