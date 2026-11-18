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
    inquired_on: null,
    ...over,
  }
}

function detail(job: ReturnType<typeof card>) {
  return {
    ...job,
    company_id: null,
    description: `About ${job.title}: build services.`,
    city: 'Pune',
    country: 'IN',
    skills_found: [],
    years_found: null,
    canonical_url: null,
    injection_flags: [],
    decision_history: [],
    first_search_id: null,
  }
}

type Setup = {
  status?: typeof STATUS
  jobs?: ReturnType<typeof card>[]
  next?: string | null
  url?: string
  files?: unknown[]
}

function renderPage({
  status = STATUS,
  jobs = [],
  next = null,
  url = '/',
  files = [],
}: Setup = {}) {
  const calls = stubApi((call: Call) => {
    if (call.path === '/status') return status
    if (call.path === '/resumes') return files
    if (call.path === '/pipeline/resumes') return { last_choice: null, usage: [] }
    if (call.method === 'POST' && /^\/jobs\/[^/]+\/(applied|inquired)$/.test(call.path))
      return jobs[0] ?? card('1', 'Backend Engineer')
    if (call.path === '/onboarding') return { display_name: null }
    if (call.path === '/search/latest') return null
    if (call.path.startsWith('/jobs/duplicates')) return { items: [], next_cursor: null }
    if (call.path.startsWith('/jobs?')) return { items: jobs, next_cursor: next }
    const one = /^\/jobs\/([^/?]+)$/.exec(call.path)
    if (one) return detail(jobs.find((j) => j.id === one[1]) ?? card(one[1] ?? 'x', 'Job'))
    if (call.path.endsWith('/interview')) return undefined
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
      <MemoryRouter initialEntries={[url]}>
        <ExplorePage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
  return calls
}

afterEach(() => vi.unstubAllGlobals())

/** The job rows of the table (not the header row, not an opened row's details). */
async function jobRows(): Promise<HTMLElement[]> {
  const table = await screen.findByRole('table', { name: 'Jobs' })
  return within(table)
    .getAllByRole('row')
    .filter((row) => within(row).queryAllByRole('columnheader').length === 0)
    .filter((row) => row.querySelector('td[colspan]') === null)
}

describe('ExplorePage', () => {
  it('US4_add_a_job_button_opens_and_closes_the_paste_form', async () => {
    const user = userEvent.setup()
    renderPage({ jobs: [card('1', 'Backend Engineer')] })

    await user.click(await screen.findByRole('button', { name: 'Add a job' }))
    expect(screen.getByLabelText('Link to the job')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(screen.queryByLabelText('Link to the job')).not.toBeInTheDocument()
  })

  it('US1 AS1 the Explore tab is lit on its own page', async () => {
    renderPage({ url: '/explore' })

    const tabs = await screen.findByRole('navigation', { name: 'Home tabs' })

    expect(within(tabs).getByRole('link', { name: 'Explore' })).toHaveAttribute(
      'aria-current',
      'page',
    )
    expect(within(tabs).getByRole('link', { name: 'In pipeline' })).not.toHaveAttribute(
      'aria-current',
    )
  })

  it('US1_AS1_lists_newest_first_with_reason', async () => {
    renderPage({
      jobs: [card('1', 'Backend Engineer'), card('2', 'Python Developer')],
    })

    const items = await jobRows()
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
    ).toHaveAttribute('href', 'https://jobs.example.com/1')
  })

  it('US1_AS10_empty_state_offers_search', async () => {
    renderPage({ jobs: [] })
    expect(await screen.findByText(/No jobs fetched yet\./)).toBeInTheDocument()
    expect(screen.getByText(/Search now\./)).toBeInTheDocument()
  })

  it('FR006_names_the_missing_search_rules_step_with_a_link', async () => {
    renderPage({
      status: {
        ...STATUS,
        checklist: { ...STATUS.checklist, rules_approved: false },
      },
    })
    expect(await screen.findByText(/search rules are not approved yet/i)).toBeInTheDocument()
    expect(screen.queryByText(/Finish setup first/)).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Review your search rules' })).toHaveAttribute(
      'href',
      '/profile/search-rules',
    )
  })

  it('FR006_names_the_missing_ai_key_first', async () => {
    renderPage({
      status: {
        ...STATUS,
        checklist: { ...STATUS.checklist, key_ok: false, rules_approved: false },
      },
    })
    expect(await screen.findByText(/AI key is not working yet/i)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Check the AI key' })).toHaveAttribute(
      'href',
      '/settings',
    )
    // only the first missing step is named
    expect(screen.queryByRole('link', { name: 'Review your search rules' })).not.toBeInTheDocument()
  })

  it('FR006_names_the_missing_preferences_step', async () => {
    renderPage({
      status: {
        ...STATUS,
        checklist: { ...STATUS.checklist, preferences_saved: false, rules_approved: false },
      },
    })
    expect(await screen.findByRole('link', { name: 'Set your preferences' })).toHaveAttribute(
      'href',
      '/profile/preferences',
    )
  })

  it('US1_AS1_shows_search_now_once_rules_are_approved', async () => {
    renderPage({ jobs: [] })
    expect(await screen.findByRole('button', { name: 'Search now' })).toBeInTheDocument()
    expect(screen.queryByText(/Finish setup first/)).not.toBeInTheDocument()
  })

  it('never_shows_the_setup_checklist_on_explore', async () => {
    renderPage({
      status: {
        ...STATUS,
        checklist: { ...STATUS.checklist, rules_approved: false },
      },
    })
    await screen.findByText(/search rules are not approved yet/i)
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
    const items = await jobRows()

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
    await screen.findByRole('table', { name: 'Jobs' })

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

  it('explore_shows_and_clears_the_company_filter', async () => {
    const user = userEvent.setup()
    const calls = renderPage({
      jobs: [card('1', 'Backend Engineer')],
      url: '/?company_id=c1',
    })

    expect(await screen.findByText('Company: Acme')).toBeInTheDocument()
    await waitFor(() => {
      const first = calls.find((c) => c.path.startsWith('/jobs?'))
      expect(first?.path).toContain('company_id=c1')
      expect(first?.path).not.toContain('area')
    })

    await user.click(screen.getByRole('button', { name: 'Remove the company filter' }))

    expect(screen.queryByText(/Company: Acme/)).toBeNull()
    await waitFor(() => {
      const last = [...calls].reverse().find((c) => c.path.startsWith('/jobs?'))
      expect(last?.path).not.toContain('company_id')
      expect(last?.path).not.toContain('area')
    })
  })

  const FILE = {
    id: 'f1',
    kind: 'upload_pdf',
    original_name: 'Backend_2025.pdf',
    size_bytes: 1000,
    page_count: 1,
    parse_status: 'parsed',
    parse_result: null,
    created_at: '2026-10-02T09:00:00Z',
    has_open_review: false,
    open_review_id: null,
  }

  it('FR001 explore row shows only two actions', async () => {
    const calls = renderPage({
      jobs: [card('1', 'Backend Engineer'), card('2', 'Platform Engineer')],
      files: [FILE],
    })

    const rows = await jobRows()
    await waitFor(() => expect(calls.some((c) => c.path === '/resumes')).toBe(true))
    for (const row of rows) {
      expect(within(row).getByRole('button', { name: 'I applied' })).toBeInTheDocument()
      expect(within(row).getByRole('button', { name: 'I inquired' })).toBeInTheDocument()
      expect(within(row).queryByRole('combobox')).not.toBeInTheDocument()
      expect(within(row).queryByRole('button', { name: /date/i, hidden: false })).toBeNull()
    }
  })

  it('FR002 details record resume and date', async () => {
    const user = userEvent.setup()
    const calls = renderPage({ jobs: [card('1', 'Backend Engineer')], files: [FILE] })
    const row = (await jobRows())[0] as HTMLElement
    await user.click(within(row).getByRole('button', { name: /show details/i }))

    const select = await screen.findByRole('combobox', {
      name: 'Resume used for Backend Engineer',
    })
    await user.selectOptions(select, 'f1')
    await user.click(screen.getByRole('button', { name: 'Pick a date' }))
    const day = new Date()
    day.setDate(day.getDate() - 3)
    const iso = `${day.getFullYear()}-${String(day.getMonth() + 1).padStart(2, '0')}-${String(day.getDate()).padStart(2, '0')}`
    const date = screen.getByLabelText('Date')
    await user.clear(date)
    await user.type(date, iso)
    const details = screen.getByRole('heading', { name: 'Record it' }).closest('section')
    await user.click(within(details as HTMLElement).getByRole('button', { name: 'I applied' }))

    await waitFor(() => expect(calls.some((c) => c.path === '/jobs/1/applied')).toBe(true))
    expect(calls.find((c) => c.path === '/jobs/1/applied')).toMatchObject({
      body: { applied_on: iso, resume_file_id: 'f1' },
    })
  })

  it('FR002 details hide the resume choice with no stored resume', async () => {
    const user = userEvent.setup()
    const calls = renderPage({ jobs: [card('1', 'Backend Engineer')], files: [] })
    const row = (await jobRows())[0] as HTMLElement
    await user.click(within(row).getByRole('button', { name: /show details/i }))

    expect(await screen.findByRole('button', { name: 'Pick a date' })).toBeInTheDocument()
    await waitFor(() => expect(calls.some((c) => c.path === '/resumes')).toBe(true))
    expect(screen.queryByRole('combobox', { name: /Resume used/ })).not.toBeInTheDocument()
  })

  it('FR003 one click from the row is unchanged', async () => {
    const user = userEvent.setup()
    const calls = renderPage({ jobs: [card('1', 'Backend Engineer')], files: [] })
    const row = (await jobRows())[0] as HTMLElement

    await user.click(within(row).getByRole('button', { name: 'I applied' }))

    await waitFor(() => expect(calls.some((c) => c.path === '/jobs/1/applied')).toBe(true))
    const mark = calls.find((c) => c.path === '/jobs/1/applied')
    expect(mark?.body).toBeUndefined()
  })

  // --- 002i US5: a row opens in place, the title opens the posting ------------------------

  it('US5_AS1_a_row_expands_and_collapses_in_place', async () => {
    const user = userEvent.setup()
    renderPage({ jobs: [card('1', 'Backend Engineer')] })
    const row = (await jobRows())[0] as HTMLElement

    await user.click(within(row).getByRole('button', { name: /show details of backend engineer/i }))
    expect(await screen.findByText(/About Backend Engineer: build services/)).toBeInTheDocument()
    expect(
      within(row).getByRole('button', { name: /hide details of backend engineer/i }),
    ).toHaveAttribute('aria-expanded', 'true')

    await user.click(within(row).getByRole('button', { name: /hide details of backend engineer/i }))
    expect(screen.queryByText(/About Backend Engineer/)).not.toBeInTheDocument()
  })

  it('US5_AS1_clicking_the_details_does_not_close_the_row', async () => {
    const user = userEvent.setup()
    renderPage({ jobs: [card('1', 'Backend Engineer')] })
    const row = (await jobRows())[0] as HTMLElement
    await user.click(within(row).getByRole('button', { name: /show details/i }))

    await user.click(await screen.findByText(/About Backend Engineer: build services/))

    expect(screen.getByText(/About Backend Engineer: build services/)).toBeInTheDocument()
  })

  it('US5_AS2_the_title_opens_the_posting_in_a_new_tab_and_leaves_the_row_closed', async () => {
    const user = userEvent.setup()
    renderPage({ jobs: [card('1', 'Backend Engineer')] })

    const title = await screen.findByRole('link', { name: 'Backend Engineer' })
    expect(title).toHaveAttribute('href', 'https://jobs.example.com/1')
    expect(title).toHaveAttribute('target', '_blank')
    expect(title).toHaveAttribute('rel', expect.stringContaining('noopener'))
    await user.click(title)
    expect(screen.queryByText(/About Backend Engineer/)).not.toBeInTheDocument()
  })

  it('US5_AS3_the_first_found_source_is_the_title_link', async () => {
    renderPage({
      jobs: [
        card('1', 'Backend Engineer', {
          sources: [
            { kind: 'careers_page', url: 'https://acme.example.com/first' },
            { kind: 'company_board', url: 'https://jobs.example.com/second' },
          ],
        }),
      ],
    })
    expect(await screen.findByRole('link', { name: 'Backend Engineer' })).toHaveAttribute(
      'href',
      'https://acme.example.com/first',
    )
  })

  it('US5_AS4_a_job_with_no_link_has_a_plain_title', async () => {
    renderPage({
      jobs: [
        card('1', 'Backend Engineer', { sources: [] }),
        card('2', 'Data Engineer', { sources: [{ kind: 'paste', url: 'javascript:alert(1)' }] }),
      ],
    })
    expect(await screen.findByText('Backend Engineer')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Backend Engineer' })).not.toBeInTheDocument()
    // a link that is not http(s) is never made into a link
    expect(screen.queryByRole('link', { name: 'Data Engineer' })).not.toBeInTheDocument()
  })

  it('US5_AS5_the_keyboard_opens_and_closes_a_row_and_it_is_announced', async () => {
    const user = userEvent.setup()
    renderPage({ jobs: [card('1', 'Backend Engineer')] })
    const toggle = await screen.findByRole('button', { name: /show details of backend engineer/i })
    expect(toggle).toHaveAttribute('aria-expanded', 'false')

    toggle.focus()
    await user.keyboard('{Enter}')
    expect(await screen.findByText(/About Backend Engineer/)).toBeInTheDocument()
    expect(toggle).toHaveAttribute('aria-expanded', 'true')
    expect(toggle).toHaveAttribute('aria-controls')

    await user.keyboard(' ')
    expect(screen.queryByText(/About Backend Engineer/)).not.toBeInTheDocument()
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
  })

  it('US5_AS6_the_actions_are_the_rows_own_and_work_with_the_row_open', async () => {
    const user = userEvent.setup()
    const calls = renderPage({ jobs: [card('1', 'Backend Engineer')] })
    const row = (await jobRows())[0] as HTMLElement
    await user.click(within(row).getByRole('button', { name: /show details/i }))
    await screen.findByText(/About Backend Engineer/)

    // one set of buttons, not two
    expect(within(row).getAllByRole('button', { name: /i applied/i })).toHaveLength(1)
    await user.click(within(row).getByRole('button', { name: /i applied/i }))

    await waitFor(() =>
      expect(calls.some((c) => c.method === 'POST' && c.path === '/jobs/1/applied')).toBe(true),
    )
  })

  it('FR028_explore_no_longer_links_to_the_job_page', async () => {
    renderPage({ jobs: [card('1', 'Backend Engineer'), card('2', 'Data Engineer')] })
    await screen.findByText('Data Engineer')
    const links = screen.getAllByRole('link').map((a) => a.getAttribute('href') ?? '')
    expect(links.filter((href) => href.startsWith('/jobs/'))).toEqual([])
  })
})
