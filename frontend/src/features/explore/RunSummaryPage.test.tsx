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
  it('US1_AS3_summary_counts_skipped', async () => {
    renderPage()

    expect(await screen.findByText(/40 jobs found/)).toBeInTheDocument()
    expect(screen.getByText(/10 added/)).toBeInTheDocument()
    expect(screen.getByText(/25 left out by your rules/)).toBeInTheDocument()
    expect(screen.getByText(/3 already known/)).toBeInTheDocument()
    expect(screen.queryByText(/cost/i)).not.toBeInTheDocument() // SC003
  })

  it('shows_each_company_result_with_a_plain_label', async () => {
    renderPage()
    const list = await screen.findByRole('list', { name: 'Companies' })
    const items = within(list).getAllByRole('listitem')
    expect(items[0]).toHaveTextContent('Acme')
    expect(items[0]).toHaveTextContent('12 jobs')
    expect(items[1]).toHaveTextContent('Broken Co')
    expect(items[1]).toHaveTextContent('Failed')
    expect(items[1]).toHaveTextContent('board timed out')
    expect(items[2]).toHaveTextContent(/Blocked/)
    expect(items[3]).toHaveTextContent(/Check manually/)
  })

  it('US1_AS5_restore_moves_job_to_explore', async () => {
    const user = userEvent.setup()
    const calls = renderPage()

    const skipped = await screen.findByRole('list', { name: 'Skipped jobs' })
    const item = within(skipped).getByText('Sales Lead').closest('li') as HTMLElement
    expect(item).toHaveTextContent('Title is not about your roles')
    await user.click(within(item).getByRole('button', { name: 'Restore' }))

    await waitFor(() =>
      expect(calls.some((c) => c.method === 'POST' && c.path === '/jobs/j1/restore')).toBe(true),
    )
  })
})
