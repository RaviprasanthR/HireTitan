import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { stubApi } from '@/test/api'
import { AppliedPage } from './AppliedPage'
import { UndoToast } from './UndoToast'

function applied(id: string, title: string, day: string) {
  return {
    id,
    title,
    company_name: 'Acme',
    location_text: 'Pune, India',
    work_mode: 'remote',
    posted_at: null,
    first_seen_at: '2026-11-01T00:00:00Z',
    state: 'applied',
    restored: false,
    sources: [{ kind: 'company_board', url: 'https://jobs.example.com/1' }],
    decision: null,
    listed: false,
    applied_on: day,
  }
}

function renderPage() {
  let rows = [applied('a', 'Newest', '2026-11-05'), applied('b', 'Older', '2026-10-01')]
  const calls = stubApi((call) => {
    if (call.method === 'DELETE' && call.path === '/jobs/a/applied') {
      rows = rows.filter((row) => row.id !== 'a')
      return {
        ...applied('a', 'Newest', '2026-11-05'),
        state: 'explore',
        applied_on: null,
      }
    }
    if (call.path.startsWith('/jobs?')) return { items: rows, next_cursor: null }
    return undefined
  })
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <MemoryRouter>
        <AppliedPage />
        <UndoToast />
      </MemoryRouter>
    </QueryClientProvider>,
  )
  return calls
}

afterEach(() => vi.unstubAllGlobals())

describe('AppliedPage', () => {
  it('FR037_lists_applied_jobs_as_a_table_newest_first', async () => {
    const calls = renderPage()

    const table = await screen.findByRole('table', { name: 'Applied jobs' })
    expect(
      within(table)
        .getAllByRole('columnheader')
        .map((header) => header.textContent),
    ).toEqual(['Company', 'Role', 'Applied on', 'Status', 'Source', ''])
    const [, newest, older] = within(table).getAllByRole('row')
    if (!newest || !older) throw new Error('expected two rows')
    expect(within(newest).getByRole('link', { name: 'Newest' })).toBeInTheDocument()
    expect(within(older).getByRole('link', { name: 'Older' })).toBeInTheDocument()
    expect(newest).toHaveTextContent('Acme')
    expect(newest).toHaveTextContent('5 Nov 2026')
    expect(newest).toHaveTextContent('Applied')
    expect(newest).toHaveTextContent('Company job board')
    expect(calls.some((call) => call.path.includes('list=applied'))).toBe(true)
  })

  it('expanding_a_row_shows_the_description', async () => {
    const user = userEvent.setup()
    stubApi((call) => {
      if (call.path === '/jobs/a')
        return {
          ...applied('a', 'Newest', '2026-11-05'),
          description: 'Build services with Python.',
          city: 'Pune',
          country: 'IN',
          skills_found: ['Python'],
          sources: [{ kind: 'company_board', url: 'https://jobs.example.com/1', label: null }],
          decision_history: [],
          injection_flags: [],
        }
      if (call.path.startsWith('/jobs?'))
        return { items: [applied('a', 'Newest', '2026-11-05')], next_cursor: null }
      return undefined
    })
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <AppliedPage />
        </MemoryRouter>
      </QueryClientProvider>,
    )
    const toggle = await screen.findByRole('button', { name: 'Details for Newest' })
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByText('Build services with Python.')).toBeNull()

    await user.click(toggle)

    expect(await screen.findByText('Build services with Python.')).toBeInTheDocument()
    expect(toggle).toHaveAttribute('aria-expanded', 'true')
    await user.click(toggle)
    expect(screen.queryByText('Build services with Python.')).toBeNull()
  })

  it('US5_AS3_undo_returns_the_job_to_the_list', async () => {
    const user = userEvent.setup()
    const calls = renderPage()
    const table = await screen.findByRole('table', { name: 'Applied jobs' })

    const [, newest] = within(table).getAllByRole('row')
    if (!newest) throw new Error('expected a first row')
    await user.click(within(newest).getByRole('button', { name: 'Undo' }))

    await waitFor(() =>
      expect(
        calls.some((call) => call.method === 'DELETE' && call.path === '/jobs/a/applied'),
      ).toBe(true),
    )
    await waitFor(() =>
      expect(within(screen.getByRole('table', { name: 'Applied jobs' })).getAllByRole('row')).toHaveLength(2),
    )
  })

  it('says_so_when_nothing_is_applied_yet', async () => {
    stubApi((call) =>
      call.path.startsWith('/jobs?') ? { items: [], next_cursor: null } : undefined,
    )
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <AppliedPage />
        </MemoryRouter>
      </QueryClientProvider>,
    )

    expect(await screen.findByText(/haven.t marked any job as applied/i)).toBeInTheDocument()
  })
})
