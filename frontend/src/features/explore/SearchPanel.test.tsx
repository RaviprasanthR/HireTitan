import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
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

  it('the_ai_is_always_used_there_is_no_rules_only_choice', async () => {
    const user = userEvent.setup()
    const calls = renderPanel(null)

    await screen.findByRole('button', { name: 'Search now' })
    expect(screen.queryByRole('checkbox', { name: /rules only/i })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Search now' }))

    await waitFor(() =>
      expect(calls.find((c) => c.method === 'POST')?.body).toEqual({ mode: 'rules_and_ai' }),
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

  it('US2_AS2_shows_companies_checked_and_new_jobs', async () => {
    renderPanel(run())

    expect(await screen.findByText('Searching your companies…')).toBeInTheDocument()
    expect(screen.getByText('Checked 8 of 20 companies · 6 new jobs so far')).toBeInTheDocument()
    expect(screen.getByRole('progressbar', { name: 'Search progress' })).toHaveAttribute(
      'aria-valuenow',
      '40',
    )
    expect(screen.queryByText(/cost/i)).not.toBeInTheDocument() // SC003
    expect(screen.queryByRole('button', { name: 'Search now' })).not.toBeInTheDocument()
  })

  it('US2_AS1_shows_searching_and_no_zero_counts_before_a_company_is_read', async () => {
    // the plan is made (20 companies) but none is read yet: no "0 of 20"
    renderPanel(run({ companies_total: 20, companies_read: 0, added: 0 }))

    expect(await screen.findByText('Searching your companies…')).toBeInTheDocument()
    expect(screen.queryByText(/Checked/)).not.toBeInTheDocument()
    expect(screen.queryByText(/0 of/)).not.toBeInTheDocument()
    const bar = screen.getByRole('progressbar', { name: 'Search progress' })
    expect(bar).not.toHaveAttribute('aria-valuenow') // moving, amount not known
    expect(bar).toHaveAttribute('aria-busy', 'true')
  })

  it('US2_AS1_shows_searching_at_once_when_search_now_is_pressed', async () => {
    const user = userEvent.setup()
    // the server has not answered yet: the panel must already say it is searching
    renderPanel(null, (call) =>
      call.method === 'POST' && call.path === '/search/runs' ? new Promise(() => {}) : undefined,
    )

    await user.click(await screen.findByRole('button', { name: 'Search now' }))

    expect(await screen.findByText('Searching your companies…')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Search now' })).not.toBeInTheDocument()
    expect(screen.queryByText(/0 of/)).not.toBeInTheDocument()
  })

  it('US2_AS1_a_failed_start_goes_back_to_the_button', async () => {
    const user = userEvent.setup()
    renderPanel(null, (call) =>
      call.method === 'POST' && call.path === '/search/runs'
        ? problem(409, 'A search is already running.', { reason: 'search_already_running' })
        : undefined,
    )

    await user.click(await screen.findByRole('button', { name: 'Search now' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('A search is already running.')
    expect(screen.queryByText('Searching your companies…')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Search now' })).toBeInTheDocument()
  })

  it('US2_a_search_that_ends_before_it_is_seen_goes_straight_to_the_end_message', async () => {
    const user = userEvent.setup()
    let latest: unknown = null
    renderPanel(null, (call) => {
      if (call.method === 'POST' && call.path === '/search/runs')
        latest = run({
          id: 's2',
          outcome: 'finished',
          companies_total: 0,
          companies_read: 0,
          added: 0,
        })
      if (call.path === '/search/latest') return latest
      return undefined
    })

    await user.click(await screen.findByRole('button', { name: 'Search now' }))

    expect(await screen.findByText('Search finished.')).toBeInTheDocument()
    expect(screen.queryByText('Searching your companies…')).not.toBeInTheDocument()
    expect(screen.getByText('0 new jobs')).toBeInTheDocument() // no "Checked 0 of 0"
    expect(screen.queryByText(/Checked/)).not.toBeInTheDocument()
  })

  it('US2_a_second_search_after_a_finished_one_shows_searching_then_its_counts', async () => {
    const user = userEvent.setup()
    let latest: unknown = run({ id: 's1', outcome: 'finished' })
    renderPanel(null, (call) => {
      if (call.method === 'POST' && call.path === '/search/runs')
        latest = run({ id: 's2', companies_total: 10, companies_read: 3, added: 2 })
      if (call.path === '/search/latest') return latest
      return undefined
    })
    expect(await screen.findByText('Search finished.')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Search now' }))

    expect(await screen.findByText('Searching your companies…')).toBeInTheDocument()
    expect(
      await screen.findByText('Checked 3 of 10 companies · 2 new jobs so far'),
    ).toBeInTheDocument()
    expect(screen.queryByText('Search finished.')).not.toBeInTheDocument()
  })

  it('US2_a_start_can_be_retried_after_it_failed', async () => {
    const user = userEvent.setup()
    let attempts = 0
    renderPanel(null, (call) => {
      if (call.method === 'POST' && call.path === '/search/runs') {
        attempts += 1
        if (attempts === 1) return problem(409, 'A search is already running.')
        return new Promise(() => {}) // the second one is still waiting for the server
      }
      return undefined
    })

    await user.click(await screen.findByRole('button', { name: 'Search now' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('already running')
    await user.click(screen.getByRole('button', { name: 'Search now' }))

    expect(await screen.findByText('Searching your companies…')).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('US2_stop_cannot_be_pressed_twice_while_it_is_being_sent', async () => {
    const user = userEvent.setup()
    const calls = renderPanel(run(), (call) =>
      call.path.endsWith('/stop') ? new Promise(() => {}) : undefined,
    )

    const stop = await screen.findByRole('button', { name: 'Stop' })
    await user.click(stop)
    await user.click(stop)

    expect(calls.filter((c) => c.path.endsWith('/stop'))).toHaveLength(1)
  })

  it('US2_AS6_the_status_line_is_always_on_the_page_so_changes_are_announced', async () => {
    renderPanel(null)
    // no run yet: the line exists (empty) and is a polite live region
    const status = await screen.findByRole('status')
    expect(status).toHaveAttribute('aria-live', 'polite')
    expect(status).toHaveTextContent('')
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
    // US2 AS4: says jobs found so far are kept, and does not mention batches
    expect(await screen.findByText(/Stopping… jobs found so far are kept/)).toBeInTheDocument()
  })

  it('US2_AS4_shows_stopping_while_a_stop_is_requested', async () => {
    renderPanel(run({ stop_requested: true }))
    expect(await screen.findByText(/Stopping… jobs found so far are kept/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Stop' })).not.toBeInTheDocument()
  })

  it('US2_AS6_the_message_is_announced_politely_and_the_bar_is_named', async () => {
    renderPanel(run())
    const message = await screen.findByText('Searching your companies…')
    expect(message.closest('[aria-live="polite"]')).not.toBeNull()
    expect(screen.getByRole('progressbar', { name: 'Search progress' })).toBeInTheDocument()
  })

  it('SC003_the_word_batch_appears_nowhere_in_the_panel', async () => {
    const outcomes = [
      null,
      'finished',
      'stopped_by_user',
      'out_of_credit',
      'failed',
      'budget_reached',
    ]
    for (const outcome of outcomes) {
      renderPanel(run({ outcome, stop_requested: outcome === null }))
      await screen.findByRole('region', { name: 'Search' })
      await screen.findByRole('status')
      expect(document.body.textContent ?? '').not.toMatch(/batch/i)
      cleanup()
      vi.unstubAllGlobals()
    }
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

  it('an old budget_reached search shows Stopped and offers continue', async () => {
    const user = userEvent.setup()
    const calls = renderPanel(run({ outcome: 'budget_reached' }))

    expect(await screen.findByText(/Search stopped/)).toBeInTheDocument()
    expect(screen.queryByText(/budget/i)).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Continue searching' }))

    await waitFor(() =>
      expect(calls.some((c) => c.method === 'POST' && c.path === '/search/runs')).toBe(true),
    )
  })

  it('US2_AS5_finished_says_how_many_new_jobs_without_batches', async () => {
    renderPanel(run({ outcome: 'finished', batches_done: 3, companies_read: 20, added: 6 }))
    expect(await screen.findByText(/Search finished/)).toBeInTheDocument()
    expect(screen.getByText('Checked 20 of 20 companies · 6 new jobs')).toBeInTheDocument()
  })

  it('US2_AS5_a_stopped_search_says_jobs_so_far_are_kept', async () => {
    renderPanel(run({ outcome: 'stopped_by_user' }))
    expect(
      await screen.findByText('Search stopped. Jobs found so far are kept.'),
    ).toBeInTheDocument()
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
