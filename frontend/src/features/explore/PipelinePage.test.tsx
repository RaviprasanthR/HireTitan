import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { stubApi } from '@/test/api'
import { UndoToast } from '@/features/jobs/UndoToast'
import { PipelinePage } from './PipelinePage'

function applied(id: string, title: string, day: string) {
  return {
    id,
    title: `${title} (Python) - Pune`,
    role: title,
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
    inquired_on: null,
  }
}

function inquired(id: string, title: string, day: string) {
  return { ...applied(id, title, day), state: 'inquired', applied_on: null, inquired_on: day }
}

function renderPage() {
  let rows = [applied('a', 'Newest', '2026-11-05'), inquired('b', 'Older', '2026-10-01')]
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
        <PipelinePage />
        <UndoToast />
      </MemoryRouter>
    </QueryClientProvider>,
  )
  return calls
}

afterEach(() => vi.unstubAllGlobals())

describe('PipelinePage', () => {
  it('US1 AS2 pipeline lists applied and inquired', async () => {
    const calls = renderPage()

    const table = await screen.findByRole('table', { name: 'Pipeline jobs' })
    expect(
      within(table)
        .getAllByRole('columnheader')
        .map((header) => header.textContent),
    ).toEqual(['Company', 'Role', 'Date', 'Status', 'Source', ''])
    const [, newest, older] = within(table).getAllByRole('row')
    if (!newest || !older) throw new Error('expected two rows')
    expect(within(newest).getByRole('link', { name: 'Newest' })).toBeInTheDocument()
    expect(within(older).getByRole('link', { name: 'Older' })).toBeInTheDocument()
    expect(newest).toHaveTextContent('Acme')
    expect(newest).toHaveTextContent('5 Nov 2026')
    expect(newest).toHaveTextContent('Applied')
    expect(older).toHaveTextContent('Inquired')
    expect(older).toHaveTextContent('1 Oct 2026')
    expect(newest).toHaveTextContent('Company job board')
    expect(calls.some((call) => call.path.includes('list=pipeline'))).toBe(true)
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
          <PipelinePage />
        </MemoryRouter>
      </QueryClientProvider>,
    )
    const toggle = await screen.findByRole('button', { name: 'Details for Newest (Python) - Pune' })
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByText('Build services with Python.')).toBeNull()

    await user.click(toggle)

    expect(await screen.findByText('Build services with Python.')).toBeInTheDocument()
    expect(toggle).toHaveAttribute('aria-expanded', 'true')
    await user.click(toggle)
    expect(screen.queryByText('Build services with Python.')).toBeNull()
  })

  it('the_edit_icon_opens_the_job_where_the_date_can_be_changed_or_undone', async () => {
    renderPage()
    const table = await screen.findByRole('table', { name: 'Pipeline jobs' })
    const [, newest] = within(table).getAllByRole('row')
    if (!newest) throw new Error('expected a first row')
    expect(within(newest).getByRole('link', { name: /^Edit / })).toHaveAttribute('href', '/jobs/a')
  })

  it('shows_the_short_role_with_the_full_title_on_hover', async () => {
    renderPage()
    const link = await screen.findByRole('link', { name: 'Newest' })
    expect(link).toHaveAttribute('title', 'Newest (Python) - Pune')
  })

  it('shows_the_status_and_source_as_tags', async () => {
    renderPage()
    const table = await screen.findByRole('table', { name: 'Pipeline jobs' })
    const [, newest] = within(table).getAllByRole('row')
    if (!newest) throw new Error('expected a first row')
    expect(within(newest).getByText('Applied')).toHaveClass('ht-pill-green')
  })

  it('an inquired job shows an Inquired tag in its own colour', async () => {
    stubApi((call) =>
      call.path.startsWith('/jobs?')
        ? { items: [inquired('i', 'Asked', '2026-11-02')], next_cursor: null }
        : undefined,
    )
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <PipelinePage />
        </MemoryRouter>
      </QueryClientProvider>,
    )

    const tag = await screen.findByText('Inquired')

    expect(tag).toHaveClass('ht-pill-blue')
  })

  it('US1 AS3 the tab is in the address, and AS1 explore is the default tab', async () => {
    stubApi((call) =>
      call.path.startsWith('/jobs?') ? { items: [], next_cursor: null } : undefined,
    )
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter initialEntries={['/pipeline']}>
          <PipelinePage />
        </MemoryRouter>
      </QueryClientProvider>,
    )

    const tabs = await screen.findByRole('navigation', { name: 'Home tabs' })

    expect(within(tabs).getByRole('link', { name: 'Explore' })).toHaveAttribute('href', '/')
    const pipeline = within(tabs).getByRole('link', { name: 'In pipeline' })
    expect(pipeline).toHaveAttribute('href', '/pipeline')
    expect(pipeline).toHaveAttribute('aria-current', 'page')
  })

  it('US1 AS5 empty pipeline message', async () => {
    stubApi((call) =>
      call.path.startsWith('/jobs?') ? { items: [], next_cursor: null } : undefined,
    )
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <PipelinePage />
        </MemoryRouter>
      </QueryClientProvider>,
    )

    expect(
      await screen.findByText(
        'Nothing in your pipeline yet. Mark a job as applied or inquired in Explore.',
      ),
    ).toBeInTheDocument()
  })
})
