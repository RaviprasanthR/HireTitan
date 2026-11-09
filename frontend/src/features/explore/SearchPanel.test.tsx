import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { type Call, problem, stubApi } from '@/test/api'
import { SearchPanel } from './SearchPanel'

function run(over: Record<string, unknown> = {}) {
  return {
    id: 's1',
    run_id: 'r1',
    mode: 'rules_and_ai',
    outcome: null,
    stop_message: null,
    stop_requested: false,
    batches_done: 1,
    companies_total: 20,
    companies_read: 8,
    jobs_found: 40,
    skipped_by_rules: 20,
    judged_by_ai: 10,
    kept: 6,
    added: 6,
    merged: 0,
    not_checked_by_ai: 0,
    ai_cost_usd: '0.0123',
    ai_note: null,
    started_at: '2026-11-06T09:00:00Z',
    finished_at: null,
    ...over,
  }
}

function renderPanel(latest: unknown, extra?: (call: Call) => unknown) {
  const calls = stubApi((call) => {
    const custom = extra?.(call)
    if (custom !== undefined) return custom
    if (call.path === '/search/latest') return latest
    if (call.path === '/search/runs' && call.method === 'POST')
      return new Response('{"search_run_id":"s2","run_id":"r2"}', {
        status: 202,
        headers: { 'Content-Type': 'application/json' },
      })
    if (call.path.endsWith('/stop'))
      return new Response('{"stopping":true}', {
        status: 202,
        headers: { 'Content-Type': 'application/json' },
      })
    return undefined
  })
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <SearchPanel />
      </MemoryRouter>
    </QueryClientProvider>,
  )
  return calls
}

afterEach(() => vi.unstubAllGlobals())

describe('SearchPanel', () => {
  it('starts_a_search_with_one_click_and_no_cost_prompt', async () => {
    const user = userEvent.setup()
    const calls = renderPanel(null)

    await user.click(await screen.findByRole('button', { name: 'Search now' }))

    await waitFor(() =>
      expect(calls.find((c) => c.method === 'POST' && c.path === '/search/runs')?.body).toEqual({
        mode: 'rules_and_ai',
      }),
    )
  })

  it('US1_AS7_rules_only_toggle_sends_rules_only', async () => {
    const user = userEvent.setup()
    const calls = renderPanel(null)

    await user.click(await screen.findByRole('checkbox', { name: /rules only/i }))
    await user.click(screen.getByRole('button', { name: 'Search now' }))

    await waitFor(() =>
      expect(calls.find((c) => c.method === 'POST')?.body).toEqual({
        mode: 'rules_only',
      }),
    )
  })

  it('US1_AS7_rules_only_notice', async () => {
    renderPanel(
      run({
        outcome: 'finished',
        ai_note: 'AI step skipped: the AI was not available, so the rules alone decided.',
      }),
    )
    expect(await screen.findByText(/AI step skipped: the AI was not available/)).toBeInTheDocument()
  })

  it('FR008_progress_per_batch_with_cost', async () => {
    renderPanel(run())

    expect(await screen.findByText('Batch 2 of 3')).toBeInTheDocument()
    expect(screen.getByText(/8 of 20 companies read/)).toBeInTheDocument()
    expect(screen.getByText(/6 jobs added/)).toBeInTheDocument()
    expect(screen.getByText(/AI cost so far: \$0\.0123/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Search now' })).not.toBeInTheDocument()
  })

  it('US1_AS9_stop_button', async () => {
    const user = userEvent.setup()
    const calls = renderPanel(run())

    await user.click(await screen.findByRole('button', { name: 'Stop' }))

    await waitFor(() =>
      expect(calls.some((c) => c.method === 'POST' && c.path === '/search/runs/s1/stop')).toBe(
        true,
      ),
    )
    expect(await screen.findByText(/stopping after this batch/i)).toBeInTheDocument()
  })

  it('US1_AS9_shows_stopping_while_a_stop_is_requested', async () => {
    renderPanel(run({ stop_requested: true }))
    expect(await screen.findByText(/stopping after this batch/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Stop' })).not.toBeInTheDocument()
  })

  it('US1_AS8_out_of_credit_shows_provider_message', async () => {
    renderPanel(
      run({
        outcome: 'out_of_credit',
        stop_message:
          'You exceeded your current quota, please check your plan and billing details.',
      }),
    )
    expect(await screen.findByText(/out of credit/i)).toBeInTheDocument()
    expect(screen.getByText(/You exceeded your current quota/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Continue searching' })).toBeInTheDocument()
  })

  it('US1_AS8_budget_reached_offers_continue', async () => {
    const user = userEvent.setup()
    const calls = renderPanel(run({ outcome: 'budget_reached' }))

    expect(await screen.findByText(/monthly AI budget/i)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Continue searching' }))

    await waitFor(() =>
      expect(calls.some((c) => c.method === 'POST' && c.path === '/search/runs')).toBe(true),
    )
  })

  it('shows_the_summary_link_when_finished', async () => {
    renderPanel(run({ outcome: 'finished', batches_done: 3, companies_read: 20 }))
    expect(await screen.findByText(/Search finished/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /see the summary/i })).toHaveAttribute(
      'href',
      '/search/runs/s1',
    )
    expect(screen.getByRole('link', { name: /search history/i })).toHaveAttribute(
      'href',
      '/search/history',
    )
  })

  it('FR009_conflict_message', async () => {
    const user = userEvent.setup()
    renderPanel(null, (call) =>
      call.method === 'POST' && call.path === '/search/runs'
        ? problem(409, 'A search is already running.', {
            reason: 'search_already_running',
          })
        : undefined,
    )

    await user.click(await screen.findByRole('button', { name: 'Search now' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('A search is already running.')
  })
})
