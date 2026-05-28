import { act, fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { makeStep } from '../../../../test/fixtures'
import { StepDetailPanel } from './StepDetailPanel'

describe('StepDetailPanel', () => {
  it('renders LLM I/O and token details', () => {
    render(
      <StepDetailPanel
        step={makeStep({
          llm_input: [{ role: 'user', content: 'Plan a launch' }],
          llm_output: [{ role: 'assistant', content: 'Launch plan ready' }],
          tokens_in: 1_000,
          tokens_out: 250,
          llm_model: 'gpt-4o-mini',
        })}
      />,
    )

    expect(screen.getByText('LLM I/O')).toBeInTheDocument()
    expect(screen.getByText('Plan a launch')).toBeInTheDocument()
    expect(screen.getByText('Launch plan ready')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /tokens/i }))

    expect(screen.getByText('Tokens in')).toBeInTheDocument()
    expect(screen.getByText('1,000')).toBeInTheDocument()
    expect(screen.getByText('250')).toBeInTheDocument()
    expect(screen.getByText('gpt-4o-mini')).toBeInTheDocument()
  })

  it('renders tool call arguments and result', () => {
    render(
      <StepDetailPanel
        step={makeStep({
          event_type: 'tool_call',
          function_name: 'search_web',
          tool_name: 'search_web',
          tool_args: { query: 'dbos durable workflows' },
          tool_result: 'Search result payload',
          llm_model: null,
          tokens_in: null,
          tokens_out: null,
        })}
      />,
    )

    expect(screen.getByText('Tool Call')).toBeInTheDocument()
    expect(screen.getAllByText('search_web')).toHaveLength(2)
    expect(screen.getByText(/dbos durable workflows/)).toBeInTheDocument()
    expect(screen.getByText('Search result payload')).toBeInTheDocument()
  })

  it('renders explicit error messages and fallback error copy', () => {
    const { rerender } = render(
      <StepDetailPanel
        step={makeStep({
          status: 'ERROR',
          error_message: 'Validation failed',
        })}
      />,
    )

    expect(screen.getAllByText('Error')).toHaveLength(2)
    expect(screen.getByText('Validation failed')).toBeInTheDocument()

    rerender(
      <StepDetailPanel
        step={makeStep({
          status: 'ERROR',
          error_message: null,
        })}
      />,
    )

    expect(
      screen.getByText(/The backend does not yet expose the error message/),
    ).toBeInTheDocument()
  })

  it('ticks running sleep duration with fake timers', () => {
    vi.useFakeTimers()
    vi.setSystemTime(5_000)

    render(
      <StepDetailPanel
        step={makeStep({
          function_name: 'DBOS.sleep',
          event_type: 'step',
          started_at_epoch_ms: 1_000,
          completed_at_epoch_ms: null,
          display_completed_at_epoch_ms: undefined as unknown as null,
          duration_ms: null,
          display_duration_ms: undefined as unknown as null,
        })}
      />,
    )

    expect(screen.getByText('4.0')).toBeInTheDocument()
    expect(screen.getByText('seconds')).toBeInTheDocument()

    act(() => {
      vi.advanceTimersByTime(1_000)
    })

    expect(screen.getByText('5.0')).toBeInTheDocument()
  })
})
