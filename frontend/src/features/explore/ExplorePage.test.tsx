import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { type Call, STATUS, stubApi } from '@/test/api'
import { ExplorePage } from './ExplorePage'

function card(id: string, title: string, over: Record<string, unknown> = {}) {
  return {
    id,
    title,
    company_name: 'Acme',
    location_text: 'Pune, India',
    work_mode: 'remote',
    posted_at: '2026-11-04T00:00:00Z',
    first_seen_at: '2026-11-05T00:00:00Z',
    state: 'explore',
    restored: false,
    sources: [{ kind: 'company_board', url: 'https://jobs.example.com/1' }],
    decision: {
      outcome: 'shown',
      decided_by: 'ai',
      reason: 'Matches your Python skills',
    },
    listed: true,
    applied_on: null,
    ...over,
  }
}

type Setup = {
  status?: typeof STATUS
  jobs?: ReturnType<typeof card>[]
  next?: string | null
}

function renderPage({ status = STATUS, jobs = [], next = null }: Setup = {}) {
  const calls = stubApi((call: Call) => {
    if (call.path === '/status') return status
    if (call.path === '/onboarding') return { display_name: null }
    if (call.path === '/search/latest') return null
    if (call.path.startsWith('/jobs/duplicates')) return { items: [], next_cursor: null }
    if (call.path.startsWith('/jobs?')) return { items: jobs, next_cursor: next }
    if (call.path.endsWith('/recheck'))
      return new Response('{"run_id":"r1"}', {
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
        <ExplorePage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
  return calls
}

afterEach(() => vi.unstubAllGlobals())

describe('ExplorePage', () => {
  it('US1_AS1_lists_newest_first_with_reason', async () => {
    renderPage({
      jobs: [card('1', 'Backend Engineer'), card('2', 'Python Developer')],
    })

    const list = await screen.findByRole('list', { name: 'Jobs' })
    const items = within(list).getAllByRole('listitem')
    expect(items).toHaveLength(2)
    expect(items[0]).toHaveTextContent('Backend Engineer')
    expect(items[0]).toHaveTextContent('Acme')
    expect(items[0]).toHaveTextContent('Pune, India')
    expect(items[0]).toHaveTextContent('remote')
    expect(items[0]).toHaveTextContent('Matches your Python skills')
    expect(
      within(items[0] as HTMLElement).getByRole('link', {
        name: /backend engineer/i,
      }),
    ).toHaveAttribute('href', '/jobs/1')
  })

  it('US1_AS10_empty_state_offers_search', async () => {
    renderPage({ jobs: [] })
    expect(await screen.findByText(/No jobs fetched yet\./)).toBeInTheDocument()
    expect(screen.getByText(/Search now\./)).toBeInTheDocument()
  })

  it('US1_AS10_empty_state_asks_to_finish_setup_first', async () => {
    renderPage({
      status: {
        ...STATUS,
        checklist: { ...STATUS.checklist, rules_approved: false },
      },
    })
    expect(await screen.findByText(/Finish setup first/)).toBeInTheDocument()
  })

  it('US1_AS11_setup_checklist_first', async () => {
    renderPage({
      status: {
        ...STATUS,
        checklist: { ...STATUS.checklist, rules_approved: false },
      },
    })
    const checklist = await screen.findByRole('list', {
      name: 'Setup checklist',
    })
    const jobs = screen.queryByRole('list', { name: 'Jobs' })
    expect(checklist).toBeInTheDocument()
    if (jobs)
      expect(
        checklist.compareDocumentPosition(jobs) & Node.DOCUMENT_POSITION_FOLLOWING,
      ).toBeTruthy()
  })

  it('hides_the_checklist_once_setup_is_done', async () => {
    renderPage({ jobs: [card('1', 'Backend Engineer')] })
    await screen.findByRole('list', { name: 'Jobs' })
    expect(screen.queryByRole('list', { name: 'Setup checklist' })).not.toBeInTheDocument()
  })

  it('FR028_not_checked_job_offers_check_again', async () => {
    const user = userEvent.setup()
    const calls = renderPage({
      jobs: [
        card('1', 'Unchecked Role', {
          decision: {
            outcome: 'shown',
            decided_by: 'rules_only_fallback',
            reason: 'not checked by AI',
          },
        }),
        card('2', 'Judged Role'),
      ],
    })
    const items = within(await screen.findByRole('list', { name: 'Jobs' })).getAllByRole('listitem')

    expect(items[0]).toHaveTextContent('not checked by AI')
    await user.click(
      within(items[0] as HTMLElement).getByRole('button', {
        name: /check again/i,
      }),
    )

    await waitFor(() =>
      expect(calls.some((c) => c.method === 'POST' && c.path === '/jobs/1/recheck')).toBe(true),
    )
    expect(
      within(items[1] as HTMLElement).queryByRole('button', {
        name: /check again/i,
      }),
    ).not.toBeInTheDocument()
  })

  it('FR030_filters_and_sort', async () => {
    const user = userEvent.setup()
    const calls = renderPage({ jobs: [card('1', 'Backend Engineer')] })
    await screen.findByRole('list', { name: 'Jobs' })

    await user.selectOptions(screen.getByLabelText('Work mode'), 'remote')
    await user.selectOptions(screen.getByLabelText('Sort by'), 'company')
    await user.type(screen.getByLabelText('City'), 'Pune')

    await waitFor(() => {
      const last = [...calls].reverse().find((c) => c.path.startsWith('/jobs?'))
      expect(last?.path).toContain('work_mode=remote')
      expect(last?.path).toContain('sort=company')
      expect(last?.path).toContain('city=Pune')
    })
  })

  it('load_more_follows_the_cursor', async () => {
    const user = userEvent.setup()
    const calls = renderPage({
      jobs: [card('1', 'Backend Engineer')],
      next: 'abc',
    })
    await user.click(await screen.findByRole('button', { name: /load more/i }))
    await waitFor(() => expect(calls.some((c) => c.path.includes('cursor=abc'))).toBe(true))
  })
})
