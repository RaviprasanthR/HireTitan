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
  /** ids whose re-check the server refuses */
  recheckFails?: string[]
}

function renderPage({
  status = STATUS,
  jobs = [],
  next = null,
  url = '/',
  files = [],
  recheckFails = [],
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
        status: recheckFails.some((id) => call.path === `/jobs/${id}/recheck`) ? 500 : 202,
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

  it('test_US1_AS3_explore_rows_are_cards', async () => {
    renderPage({ jobs: [card('1', 'Backend Engineer')] })
    const table = await screen.findByRole('table', { name: 'Jobs' })
    expect(table).toHaveClass('ht-table-cards')
    const cells = (within(table).getAllByRole('row')[1] as HTMLElement).querySelectorAll(
      'td[data-label]',
    )
    expect([...cells].map((td) => td.getAttribute('data-label'))).toEqual([
      'Location',
      'Posted',
      'Source',
    ])
    // titles wrap on a phone and are cut short only from 768px
    expect(within(table).getByTitle('Backend Engineer')).toHaveClass('md:truncate')
    expect(within(table).getByTitle('Backend Engineer')).not.toHaveClass('truncate')
    expect(screen.getByRole('form', { name: 'Filters' })).toHaveClass('grid-cols-1', 'md:flex')
  })

  it('test_FR023a_only_the_explore_table_scrolls_on_a_wide_screen', async () => {
    renderPage({ jobs: [card('1', 'Backend Engineer')] })
    const table = await screen.findByRole('table', { name: 'Jobs' })
    expect(table.closest('section')).toHaveClass('ht-fit-page')
    expect(table.parentElement).toHaveClass('ht-table-scroll')
  })

  it('test_US2_AS3_title_opens_job_page', async () => {
    renderPage({ jobs: [card('1', 'Backend Engineer')] })
    const table = await screen.findByRole('table', { name: 'Jobs' })
    const title = within(table).getByRole('link', { name: 'Backend Engineer' })
    expect(title).toHaveAttribute('href', '/jobs/1')
    expect(title).not.toHaveAttribute('target')
  })

  it('a click on the title opens the job page, not the row', async () => {
    const user = userEvent.setup()
    renderPage({ jobs: [card('1', 'Backend Engineer')] })
    const table = await screen.findByRole('table', { name: 'Jobs' })
    await user.click(within(table).getByRole('link', { name: 'Backend Engineer' }))
    expect(screen.queryByText(/About Backend Engineer/)).toBeNull()
    expect(
      within(table).getByRole('button', { name: /show details of backend engineer/i }),
    ).toHaveAttribute('aria-expanded', 'false')
  })

  it('test_US2_AS4_open_posting_new_tab_and_announced', async () => {
    renderPage({ jobs: [card('1', 'Backend Engineer')] })
    const table = await screen.findByRole('table', { name: 'Jobs' })
    const posting = within(table).getByRole('link', {
      name: 'Open posting for Backend Engineer (opens in a new tab)',
    })
    expect(posting).toHaveAttribute('href', 'https://jobs.example.com/1')
    expect(posting).toHaveAttribute('target', '_blank')
    expect(posting).toHaveAttribute('rel', 'noreferrer noopener')
    expect(posting.querySelector('svg')).toHaveAttribute('aria-hidden', 'true')
  })

  it('test_FR020_no_open_posting_without_url', async () => {
    renderPage({
      jobs: [card('1', 'Backend Engineer', { sources: [{ kind: 'paste', url: null }] })],
    })
    const table = await screen.findByRole('table', { name: 'Jobs' })
    expect(within(table).getByRole('link', { name: 'Backend Engineer' })).toBeInTheDocument()
    expect(within(table).queryByRole('link', { name: /Open posting/ })).toBeNull()
  })

  it('test_FR016_detail_row_follows_its_card', async () => {
    const user = userEvent.setup()
    renderPage({ jobs: [card('1', 'Backend Engineer')] })
    const table = await screen.findByRole('table', { name: 'Jobs' })
    await user.click(within(table).getByRole('button', { name: /Show details of/ }))

    const rows = within(table).getAllByRole('row')
    expect(rows).toHaveLength(3)
    const [, row, detail] = rows as [HTMLElement, HTMLElement, HTMLElement]
    for (const td of table.querySelectorAll('td')) expect(td).toHaveAttribute('role', 'cell')
    expect(table.querySelector('tbody')).toHaveAttribute('role', 'rowgroup')
    expect(row.nextElementSibling).toBe(detail)
    expect(detail.querySelector('td[colspan]')).not.toBeNull()
  })

  it('US1 AS1 the Explore tab is lit on its own page', async () => {
    renderPage({ url: '/explore' })

    const tabs = await screen.findByRole('navigation', { name: 'Jobs tabs' })

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
      within(items[0] as HTMLElement).getByRole('link', { name: 'Backend Engineer' }),
    ).toHaveAttribute('href', '/jobs/1')
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

  it('test_US3_AS2_meta_without_dots_or_repeats', async () => {
    renderPage({
      jobs: [
        card('1', 'Backend Engineer', { location_text: 'Remote, India', work_mode: 'remote' }),
        card('2', 'Data Engineer', { location_text: null, work_mode: null, posted_at: null, sources: [] }),
        card('3', 'Platform Engineer', { location_text: 'Bengaluru (On-site)', work_mode: 'onsite' }),
      ],
    })
    const [first, second, third] = await jobRows()
    // spelling apart, "(On-site)" already says "onsite"
    expect(within(third as HTMLElement).getAllByRole('cell')[2]).toHaveTextContent(/^Bengaluru \(On-site\)$/)
    const where = within(first as HTMLElement).getAllByRole('cell')[2] as HTMLElement
    expect(where).toHaveTextContent('Remote, India')
    expect(where.textContent).not.toMatch(/[·•]/)
    expect(where.textContent?.match(/remote/gi)).toHaveLength(1)
    // an empty value reads "Not set" (FR-008)
    const empty = within(second as HTMLElement).getAllByRole('cell')
    expect(empty[2]).toHaveTextContent('Not set')
    expect(empty[3]).toHaveTextContent('Not set')
    expect(empty[4]).toHaveTextContent('Not set')
  })

  it('test_FR010_one_primary_per_view', async () => {
    renderPage({ jobs: [card('1', 'Backend Engineer'), card('2', 'Data Engineer')] })
    await jobRows()
    await screen.findByRole('button', { name: 'Search now' })
    const primaries = document.querySelectorAll(
      '[data-variant="default"], [data-variant="success"]',
    )
    expect([...primaries].map((b) => b.textContent)).toEqual(['Search now'])
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

  const unchecked = (id: string, title: string) =>
    card(id, title, {
      decision: {
        outcome: 'shown',
        decided_by: 'rules_only_fallback',
        reason: 'not checked by AI: no description yet',
      },
    })

  it('test_FR022_one_notice_with_count', async () => {
    renderPage({ jobs: [unchecked('1', 'One'), unchecked('2', 'Two'), card('3', 'Judged')] })
    const notice = await screen.findByRole('region', { name: 'Jobs not checked for fit' })
    expect(notice).toHaveTextContent('2 jobs could not be checked for fit: no description yet')
    expect(within(notice).getAllByRole('button', { name: 'Re-check fit' })).toHaveLength(1)
  })

  it('test_FR022_recheck_runs_each_job_in_turn', async () => {
    const user = userEvent.setup()
    const calls = renderPage({ jobs: [unchecked('1', 'One'), unchecked('2', 'Two')] })
    const notice = await screen.findByRole('region', { name: 'Jobs not checked for fit' })
    await user.click(within(notice).getByRole('button', { name: 'Re-check fit' }))

    // wait for the finished message, not the one shown while it runs
    expect(await within(notice).findByText(/^Asked the AI to check 2 jobs/)).toBeInTheDocument()
    const posts = calls.filter((c) => c.method === 'POST' && c.path.endsWith('/recheck'))
    expect(posts.map((c) => c.path)).toEqual(['/jobs/1/recheck', '/jobs/2/recheck'])
  })

  it('the notice keeps its live lines in the page and the button keeps focus while it runs', async () => {
    const user = userEvent.setup()
    renderPage({ jobs: [unchecked('1', 'One'), unchecked('2', 'Two')] })
    const notice = await screen.findByRole('region', { name: 'Jobs not checked for fit' })
    // a live region must exist before its text changes, or screen readers miss it (4.1.3)
    expect(within(notice).getByRole('status')).toBeEmptyDOMElement()
    expect(within(notice).getByRole('alert')).toBeEmptyDOMElement()

    const button = within(notice).getByRole('button', { name: 'Re-check fit' })
    await user.click(button)
    expect(button).not.toBeDisabled() // aria-disabled, so focus is not dropped
    expect(button).toHaveFocus()
    await within(notice).findByText(/^Asked the AI to check 2 jobs/)
  })

  it('test_FR022_rows_have_no_recheck_button', async () => {
    renderPage({ jobs: [unchecked('1', 'One')] })
    const [row] = await jobRows()
    // the reason stays as quiet text; the one action is in the notice
    expect(row).toHaveTextContent('not checked by AI: no description yet')
    expect(within(row as HTMLElement).queryByRole('button', { name: /re-check/i })).toBeNull()
  })

  it('test_FR022_partial_failure_reported', async () => {
    const user = userEvent.setup()
    renderPage({ jobs: [unchecked('1', 'One'), unchecked('2', 'Two')], recheckFails: ['2'] })
    const notice = await screen.findByRole('region', { name: 'Jobs not checked for fit' })
    await user.click(within(notice).getByRole('button', { name: 'Re-check fit' }))

    expect(
      await within(notice).findByText(
        '1 of 2 jobs could not be sent for a check. Try again later.',
      ),
    ).toHaveAttribute('role', 'alert')
  })

  it('without unchecked jobs there is no notice', async () => {
    renderPage({ jobs: [card('1', 'Judged')] })
    await jobRows()
    expect(screen.queryByRole('region', { name: 'Jobs not checked for fit' })).toBeNull()
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

  it('US5_AS3_the_first_found_source_is_the_posting_link', async () => {
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
    expect(
      await screen.findByRole('link', { name: /^Open posting for Backend Engineer/ }),
    ).toHaveAttribute('href', 'https://acme.example.com/first')
  })

  it('US5_AS4_a_job_with_no_safe_link_has_no_posting_link', async () => {
    renderPage({
      jobs: [
        card('1', 'Backend Engineer', { sources: [] }),
        card('2', 'Data Engineer', { sources: [{ kind: 'paste', url: 'javascript:alert(1)' }] }),
      ],
    })
    expect(await screen.findByText('Backend Engineer')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /Open posting for Backend/ })).toBeNull()
    // a link that is not http(s) is never made into a link
    expect(screen.queryByRole('link', { name: /Open posting for Data/ })).toBeNull()
    expect(screen.queryByRole('link', { name: /javascript/ })).toBeNull()
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

  it('FR019 Email alerts filter', async () => {
    const user = userEvent.setup()
    const calls = renderPage({
      jobs: [
        card('a1', 'Data Engineer', {
          sources: [
            {
              kind: 'email_alert',
              url: 'https://www.linkedin.com/jobs/view/3978721496/',
              site: 'linkedin',
              alert_date: '2026-11-17T05:00:00Z',
            },
          ],
        }),
      ],
    })

    await user.selectOptions(await screen.findByLabelText('Source'), 'email_alert')

    await waitFor(() =>
      expect(
        calls.some((c) => c.path.startsWith('/jobs?') && c.path.includes('source=email_alert')),
      ).toBe(true),
    )
    expect(screen.getByRole('option', { name: 'Email alerts' })).toBeInTheDocument()
  })

  it('FR019 an alert job says where it came from', async () => {
    renderPage({
      jobs: [
        card('a1', 'Data Engineer', {
          sources: [
            {
              kind: 'email_alert',
              url: 'https://www.linkedin.com/jobs/view/3978721496/',
              site: 'linkedin',
              alert_date: '2026-11-17T05:00:00Z',
            },
          ],
        }),
      ],
    })

    const [row] = await jobRows()
    expect(within(row as HTMLElement).getByText('Email alert')).toBeInTheDocument()
    expect(within(row as HTMLElement).getByText(/LinkedIn/)).toBeInTheDocument()
  })

  it('FR020 may have closed tag', async () => {
    renderPage({
      jobs: [
        card('a1', 'Old Job', { may_have_closed: true }),
        card('a2', 'Fresh Job', { may_have_closed: false }),
      ],
    })

    const rows = await jobRows()
    expect(within(rows[0] as HTMLElement).getByText('May have closed')).toBeInTheDocument()
    expect(within(rows[1] as HTMLElement).queryByText('May have closed')).not.toBeInTheDocument()
  })
})
