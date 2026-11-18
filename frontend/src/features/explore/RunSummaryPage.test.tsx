import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { stubApi } from '@/test/api'
import { RunSummaryPage } from './RunSummaryPage'

const RUN = {
  id: 's1',
  run_id: 'r1',
  mode: 'rules_and_ai',
  outcome: 'finished',
  stop_message: null,
  stop_requested: false,
  batches_done: 3,
  companies_total: 3,
  companies_read: 3,
  jobs_found: 40,
  skipped_by_rules: 25,
  judged_by_ai: 12,
  kept: 8,
  added: 10,
  merged: 3,
  not_checked_by_ai: 2,
  ai_note: null,
  started_at: '2026-11-06T09:00:00Z',
  finished_at: '2026-11-06T09:10:00Z',
  companies: [
    {
      company_id: 'c1',
      company_name: 'Acme',
      batch_no: 1,
      result: 'ok',
      jobs_found: 12,
      error: null,
    },
    {
      company_id: 'c2',
      company_name: 'Broken Co',
      batch_no: 1,
      result: 'failed',
      jobs_found: 0,
      error: 'board timed out',
    },
    {
      company_id: 'c3',
      company_name: 'Walled Inc',
      batch_no: 2,
      result: 'blocked',
      jobs_found: 0,
      error: null,
    },
    {
      company_id: 'c4',
      company_name: 'Script Ltd',
      batch_no: 2,
      result: 'unreadable',
      jobs_found: 0,
      error: null,
    },
  ],
}

function skippedJob(id: string, title: string, reason: string) {
  return {
    id,
    title,
    company_name: 'Acme',
    location_text: 'Pune',
    work_mode: null,
    posted_at: null,
    first_seen_at: '2026-11-06T00:00:00Z',
    state: 'skipped',
    restored: false,
    sources: [],
    decision: { outcome: 'skipped', decided_by: 'rule', reason },
    listed: true,
    applied_on: null,
  }
}

function renderPage() {
  const calls = stubApi((call) => {
    if (call.path === '/search/runs/s1') return RUN
    if (call.path.startsWith('/search/runs/s1/skipped'))
      return {
        items: [skippedJob('j1', 'Sales Lead', 'Title is not about your roles')],
        next_cursor: null,
      }
    if (call.path === '/jobs/j1/restore')
      return { ...skippedJob('j1', 'Sales Lead', 'x'), state: 'explore' }
    return undefined
  })
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <MemoryRouter initialEntries={['/search/runs/s1']}>
        <Routes>
          <Route path="/search/runs/:id" element={<RunSummaryPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
  return calls
}

afterEach(() => vi.unstubAllGlobals())

describe('RunSummaryPage', () => {
  it('US1_AS3_shows_the_search_as_a_flow_of_steps', async () => {
    renderPage()

    const flow = await screen.findByRole('list', { name: 'How the search went' })
    const steps = within(flow).getAllByRole('listitem')
    expect(steps.map((step) => step.textContent)).toEqual([
      expect.stringMatching(/3 of 3.*Companies read.*3 to check by hand/),
      expect.stringMatching(/40.*Jobs found/),
      expect.stringMatching(/25 left out.*Your rules/),
      expect.stringMatching(/12 checked.*AI check.*4 left out/),
      expect.stringMatching(/10.*New jobs.*3 already known/),
    ])
    expect(screen.queryByText(/cost/i)).not.toBeInTheDocument() // SC003
    expect(screen.queryByText(/batch/i)).not.toBeInTheDocument()
  })

  it('shows_what_happened_to_the_jobs_as_one_bar_with_a_legend', async () => {
    renderPage()
    const bar = await screen.findByRole('img', { name: /10 new, 3 already known, 29 left out/ })
    expect(bar).toBeInTheDocument()
    const legend = screen.getByRole('list', { name: 'Legend' })
    expect(within(legend).getByText('New jobs').parentElement).toHaveTextContent('10')
    expect(within(legend).getByText('Already known').parentElement).toHaveTextContent('3')
    expect(within(legend).getByText('Left out').parentElement).toHaveTextContent('29')
  })

  it('keeps_the_details_hidden_until_asked', async () => {
    const user = userEvent.setup()
    renderPage()
    const toggle = await screen.findByRole('button', { name: 'Show details' })
    expect(screen.queryByRole('list', { name: 'Companies to check' })).not.toBeInTheDocument()

    await user.click(toggle)

    const list = screen.getByRole('list', { name: 'Companies to check' })
    const items = within(list).getAllByRole('listitem')
    expect(items).toHaveLength(3)
    expect(items[0]).toHaveTextContent('Broken Co')
    expect(items[0]).toHaveTextContent('board timed out')
    expect(items[1]).toHaveTextContent(/Blocked/)
    expect(items[2]).toHaveTextContent(/Check manually/)
    expect(screen.getByText(/2 jobs were not checked by the AI/)).toBeInTheDocument()
    const all = screen.getByText('All 4 companies').closest('details') as HTMLElement
    expect(within(all).getByText('Acme').closest('li')).toHaveTextContent('12 jobs')
    expect(screen.getByRole('button', { name: 'Hide details' })).toBeInTheDocument()
  })

  it('has_back_and_search_history_at_the_top', async () => {
    renderPage()
    expect(await screen.findByRole('button', { name: 'Back' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Search history' })).toHaveAttribute(
      'href',
      '/search/history',
    )
  })

  it('US1_AS5_restore_moves_job_to_explore', async () => {
    const user = userEvent.setup()
    const calls = renderPage()

    await user.click(await screen.findByRole('button', { name: 'Show details' }))
    await user.click(screen.getByText('Jobs left out (29)'))
    const skipped = await screen.findByRole('list', { name: 'Skipped jobs' })
    const item = within(skipped).getByText('Sales Lead').closest('li') as HTMLElement
    expect(item).toHaveTextContent('Title is not about your roles')
    await user.click(within(item).getByRole('button', { name: 'Restore' }))

    await waitFor(() =>
      expect(calls.some((c) => c.method === 'POST' && c.path === '/jobs/j1/restore')).toBe(true),
    )
  })
})
