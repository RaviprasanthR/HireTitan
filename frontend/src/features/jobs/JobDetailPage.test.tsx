import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { act } from 'react'
import { MemoryRouter, Route, RouterProvider, Routes, createMemoryRouter } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { problem, stubApi, type Call } from '@/test/api'
import { JobDetailPage } from './JobDetailPage'
import { UndoToast } from './UndoToast'

function detail(over: Record<string, unknown> = {}) {
  return {
    id: 'j1',
    title: 'Backend Engineer',
    company_name: 'Acme',
    company_id: null,
    location_text: 'Pune, India',
    work_mode: 'remote',
    posted_at: '2026-11-04T00:00:00Z',
    first_seen_at: '2026-11-05T00:00:00Z',
    state: 'explore',
    restored: false,
    sources: [
      { kind: 'company_board', url: 'https://jobs.example.com/acme/1' },
      { kind: 'careers_page', url: 'https://acme.example.com/careers/1' },
    ],
    decision: { outcome: 'shown', decided_by: 'ai', reason: 'Matches your Python skills' },
    listed: true,
    applied_on: null,
    inquired_on: null,
    description: 'Build APIs.\n\nUse Python.',
    city: 'Pune',
    country: 'IN',
    skills_found: ['python'],
    years_found: '2',
    canonical_url: 'https://jobs.example.com/acme/1',
    injection_flags: [],
    decision_history: [
      {
        outcome: 'shown',
        decided_by: 'rules_only_fallback',
        reason: 'not checked by AI',
        created_at: '2026-11-05T00:00:00Z',
        is_current: false,
        prompt_name: null,
        prompt_version: null,
        provider: null,
        model: null,
      },
      {
        outcome: 'shown',
        decided_by: 'ai',
        reason: 'Matches your Python skills',
        created_at: '2026-11-06T00:00:00Z',
        is_current: true,
        prompt_name: 'judge_relevance',
        prompt_version: '1',
        provider: 'openai',
        model: 'gpt-5.4-mini',
      },
    ],
    first_search_id: 's1',
    ...over,
  }
}

function renderPage(
  job = detail(),
  interview: unknown = undefined,
  extra?: (call: Call) => unknown,
) {
  const calls = stubApi((call) => {
    const more = extra?.(call)
    if (more !== undefined) return more
    if (call.path === '/jobs/j1/interview')
      return typeof interview === 'function' ? interview() : interview
    if (call.path === '/jobs/j1/recheck')
      return new Response('{"run_id":"r1"}', {
        status: 202,
        headers: { 'Content-Type': 'application/json' },
      })
    if (call.path === '/jobs/j1/applied')
      return call.method === 'DELETE'
        ? { ...job, state: 'explore', applied_on: null }
        : {
            ...job,
            state: 'applied',
            applied_on:
              (call.body as { applied_on?: string } | undefined)?.applied_on ?? '2026-11-06',
          }
    if (call.path === '/jobs/j1/inquired') {
      if (call.method === 'DELETE') return { ...job, state: 'explore', inquired_on: null }
      const day = (call.body as { inquired_on?: string } | undefined)?.inquired_on
      if (day === '2999-01-01')
        return problem(422, 'The date cannot be in the future.', {
          errors: [{ field: 'inquired_on', message: 'The date cannot be in the future.' }],
        })
      return { ...job, state: 'inquired', inquired_on: day ?? '2026-11-06' }
    }
    if (call.path === '/jobs/j1') return job
    if (call.path === '/companies/c1/contacts')
      return {
        items: [
          {
            id: 'k1',
            company_id: 'c1',
            name: 'Jane Example',
            role: 'Recruiter',
            linkedin_url: null,
            email: null,
            phone: null,
            confidence: null,
            note: null,
            source: 'typed',
            updated_at: '2026-11-09T09:00:00Z',
          },
        ],
        note: { body: 'Prefers email.', source: 'typed', updated_at: '2026-11-09T09:00:00Z' },
      }
    return undefined
  })
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <MemoryRouter initialEntries={['/jobs/j1']}>
        <Routes>
          <Route path="/jobs/:id" element={<JobDetailPage />} />
        </Routes>
        <UndoToast />
      </MemoryRouter>
    </QueryClientProvider>,
  )
  return calls
}

afterEach(() => vi.unstubAllGlobals())

describe('JobDetailPage', () => {
  it('FR032_shows_sources_reason_and_original_link', async () => {
    renderPage()

    expect(
      await screen.findByRole('heading', { level: 1, name: 'Backend Engineer' }),
    ).toBeInTheDocument()
    expect(screen.getByText(/Build APIs\./)).toBeInTheDocument()
    expect(screen.getByText('Matches your Python skills')).toBeInTheDocument()
    const original = screen.getByRole('link', { name: 'Open posting (opens in a new tab)' })
    expect(original).toHaveAttribute('href', 'https://jobs.example.com/acme/1')
    expect(original).toHaveAttribute('rel', expect.stringContaining('noopener'))
    expect(original).toHaveAttribute('target', '_blank')
    const sources = screen.getByRole('list', { name: 'Sources' })
    expect(within(sources).getAllByRole('link')).toHaveLength(2)
    expect(screen.getByRole('link', { name: /first found/i })).toHaveAttribute(
      'href',
      '/search/runs/s1',
    )
    const history = screen.getByRole('list', { name: 'Decision history' })
    expect(within(history).getAllByRole('listitem')).toHaveLength(2)
  })

  it('test_FR004_job_page_shows_stage_chip', async () => {
    renderPage(detail({ state: 'applied', applied_on: '2026-11-06' }))
    const title = await screen.findByRole('heading', { level: 1, name: 'Backend Engineer' })
    // the chip sits in the page's header, before any section
    const chip = (title.parentElement as HTMLElement).querySelector('.ht-stage-chip')
    expect(chip).toHaveTextContent('Applied')
    expect(chip).toHaveAttribute('data-stage', 'applied')
    expect(document.querySelectorAll('.ht-stage-chip')).toHaveLength(1)
    // the day is a figure
    const day = screen.getByText(
      (_, el) => el?.textContent === 'Applied on 6 Nov 2026' && el.tagName === 'SPAN',
    )
    expect(within(day).getByText('6 Nov 2026')).toHaveClass('ht-figure')
  })

  it('test_US3_AS2_job_facts_without_dots_or_repeats', async () => {
    renderPage(detail({ location_text: 'Remote, India', work_mode: 'remote' }))
    const title = await screen.findByRole('heading', { level: 1, name: 'Backend Engineer' })
    const facts = title.nextElementSibling as HTMLElement
    expect(facts).toHaveTextContent('Remote, India')
    expect(facts.textContent).not.toMatch(/[·•]/)
    expect(facts.textContent?.match(/remote/gi)).toHaveLength(1)
    const history = screen.getByRole('list', { name: 'Decision history' })
    expect(history.textContent).not.toMatch(/[·•]/)
  })

  it('test_US3_AS3_job_cards_have_no_stripe', async () => {
    renderPage()
    await screen.findByRole('heading', { level: 1, name: 'Backend Engineer' })
    expect(document.querySelector('[class*="ht-section-"]')).toBeNull()
  })

  it('test_FR010_one_primary_per_view', async () => {
    renderPage(detail({ company_id: 'c1' }))
    await screen.findByLabelText('Note about Acme')
    const primaries = document.querySelectorAll(
      '[data-variant="default"], [data-variant="success"]',
    )
    expect([...primaries].map((b) => b.textContent)).toEqual(['I applied'])
  })

  it('US2 AS5 job detail shows company contacts and note', async () => {
    renderPage(detail({ company_id: 'c1' }))

    const heading = await screen.findByRole('heading', { name: 'People at Acme' })
    expect(heading).toBeInTheDocument()
    expect(await screen.findByText('Jane Example')).toBeInTheDocument()
    expect(screen.getByLabelText('Note about Acme')).toHaveValue('Prefers email.')
  })

  it('pasted job with no company shows no panel', async () => {
    const calls = renderPage(detail({ company_id: null }))

    await screen.findByRole('heading', { level: 1, name: 'Backend Engineer' })

    expect(screen.queryByRole('heading', { name: /People at/ })).toBeNull()
    expect(calls.some((c) => c.path.includes('/contacts'))).toBe(false)
  })

  it('FR038_shows_injection_warning', async () => {
    renderPage(
      detail({
        injection_flags: [
          {
            rule_id: 'ai_instruction',
            severity: 'high',
            excerpt: 'ignore previous instructions',
            location: 'description',
          },
        ],
      }),
    )
    const warning = await screen.findByRole('alert')
    expect(warning).toHaveTextContent(/instructions to an AI/i)
    expect(warning).toHaveTextContent(/ignore previous instructions/)
  })

  it('no_warning_for_a_clean_posting', async () => {
    renderPage()
    await screen.findByRole('heading', { level: 1, name: 'Backend Engineer' })
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('FR028_not_checked_job_offers_check_again', async () => {
    const user = userEvent.setup()
    const calls = renderPage(
      detail({
        decision: {
          outcome: 'shown',
          decided_by: 'rules_only_fallback',
          reason: 'not checked by AI',
        },
      }),
    )

    await user.click(await screen.findByRole('button', { name: /re-check fit/i }))

    await waitFor(() => expect(calls.some((c) => c.path === '/jobs/j1/recheck')).toBe(true))
  })

  it('test_FR020_no_open_posting_without_url', async () => {
    renderPage(detail({ canonical_url: null, sources: [] }))
    await screen.findByRole('heading', { level: 1, name: 'Backend Engineer' })
    expect(screen.queryByRole('link', { name: /Open posting/ })).not.toBeInTheDocument()
  })

  it('US5_AS1_i_applied_marks_the_job_with_today', async () => {
    const user = userEvent.setup()
    const calls = renderPage()

    await user.click(await screen.findByRole('button', { name: 'I applied' }))

    await waitFor(() =>
      expect(calls.some((c) => c.method === 'POST' && c.path === '/jobs/j1/applied')).toBe(true),
    )
    const post = calls.find((c) => c.method === 'POST' && c.path === '/jobs/j1/applied')
    expect(post?.body).toBeUndefined()
    expect(await screen.findByRole('status')).toHaveTextContent(/marked as applied/i)
  })

  it('US5_AS1_the_date_can_be_changed', async () => {
    const user = userEvent.setup()
    const calls = renderPage()

    await user.click(await screen.findByRole('button', { name: 'Pick a date' }))
    const date = screen.getByLabelText('Date')
    await user.clear(date)
    await user.type(date, '2026-11-03')
    await user.click(screen.getByRole('button', { name: 'I applied' }))

    await waitFor(() =>
      expect(calls.find((c) => c.method === 'POST' && c.path === '/jobs/j1/applied')?.body).toEqual(
        { applied_on: '2026-11-03' },
      ),
    )
  })

  it('US5_AS3_undo_from_the_notice', async () => {
    const user = userEvent.setup()
    const calls = renderPage()
    await user.click(await screen.findByRole('button', { name: 'I applied' }))

    const notice = await screen.findByRole('status')
    await user.click(within(notice).getByRole('button', { name: 'Undo' }))

    await waitFor(() =>
      expect(calls.some((c) => c.method === 'DELETE' && c.path === '/jobs/j1/applied')).toBe(true),
    )
  })

  it('US5_AS4_pasted_job_can_be_marked_applied', async () => {
    renderPage(
      detail({
        sources: [{ kind: 'paste', url: 'https://jobs.example.com/pasted' }],
        decision: { outcome: 'shown', decided_by: 'person', reason: 'added by you' },
      }),
    )

    expect(await screen.findByRole('button', { name: 'I applied' })).toBeInTheDocument()
  })

  it('a_skipped_job_can_be_marked_applied', async () => {
    renderPage(detail({ state: 'skipped' }))

    expect(await screen.findByRole('button', { name: 'I applied' })).toBeInTheDocument()
  })

  it('an_applied_job_shows_its_date_and_undo_instead', async () => {
    renderPage(detail({ state: 'applied', applied_on: '2026-11-03' }))

    expect(await screen.findByText(
      (_, el) => el?.textContent === 'Applied on 3 Nov 2026' && el.tagName === 'SPAN',
    )).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Undo' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'I applied' })).not.toBeInTheDocument()
  })

  it('US1 AS5 job page shows the same panel', async () => {
    renderPage(detail({ state: 'applied', applied_on: '2026-11-06' }), {
      job_id: 'j1',
      can_edit: true,
      can_add_round: true,
      contact: { name: 'Asha Rao', role: null, email: null, phone: null, linkedin_url: null },
      source: { kind: 'direct', firm_name: null },
      rounds: [],
      status: { state: 'applied', round: null },
      resume: { state: 'none', resume_file_id: null, name: null, added_on: null },
    })

    expect(await screen.findByRole('heading', { name: 'Interview details' })).toBeInTheDocument()
    expect(await screen.findByLabelText('Contact name')).toHaveValue('Asha Rao')
    expect(screen.getByLabelText('Contact name')).toBeEnabled()
    expect(screen.getByRole('radio', { name: 'Direct' })).toBeChecked()
  })

  it('review: marking the job applied refreshes the panel so it becomes editable', async () => {
    const user = userEvent.setup()
    let calls: Call[] = []
    const answer = () => {
      const marked = calls.some((c) => c.method === 'POST' && c.path === '/jobs/j1/applied')
      return {
        job_id: 'j1',
        can_edit: marked,
        can_add_round: marked,
        contact: { name: 'Asha Rao', role: null, email: null, phone: null, linkedin_url: null },
        source: null,
        rounds: [],
        status: { state: marked ? 'applied' : 'explore', round: null },
        resume: { state: 'none', resume_file_id: null, name: null, added_on: null },
      }
    }
    calls = renderPage(detail({ state: 'explore' }), answer)
    expect(await screen.findByLabelText('Contact name')).toBeDisabled()

    await user.click(await screen.findByRole('button', { name: 'I applied' }))

    await waitFor(() => expect(screen.getByLabelText('Contact name')).toBeEnabled())
  })

  it('US4 AS4 the panel is read-only outside the pipeline', async () => {
    renderPage(detail({ state: 'explore' }), {
      job_id: 'j1',
      can_edit: false,
      can_add_round: false,
      contact: { name: 'Asha Rao', role: null, email: null, phone: null, linkedin_url: null },
      source: null,
      rounds: [],
      status: { state: 'explore', round: null },
      resume: { state: 'none', resume_file_id: null, name: null, added_on: null },
    })

    expect(await screen.findByLabelText('Contact name')).toBeDisabled()
    expect(screen.queryByRole('button', { name: 'Save contact' })).not.toBeInTheDocument()
  })

  it('no interview panel on a job outside the pipeline that has no details', async () => {
    renderPage(detail({ state: 'explore' }), {
      job_id: 'j1',
      can_edit: false,
      can_add_round: false,
      contact: null,
      source: null,
      rounds: [],
      status: { state: 'explore', round: null },
      resume: { state: 'none', resume_file_id: null, name: null, added_on: null },
    })
    await screen.findByRole('heading', { name: 'Description' })

    expect(screen.queryByRole('heading', { name: 'Interview details' })).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Contact name')).not.toBeInTheDocument()
  })

  it('US2 AS1 I inquired moves the job to the pipeline', async () => {
    const user = userEvent.setup()
    const calls = renderPage()

    await user.click(await screen.findByRole('button', { name: 'I inquired' }))

    await waitFor(() =>
      expect(calls.some((c) => c.method === 'POST' && c.path === '/jobs/j1/inquired')).toBe(true),
    )
    expect(calls.find((c) => c.path === '/jobs/j1/inquired')?.body).toBeUndefined() // today
    expect(await screen.findByRole('status')).toHaveTextContent(/marked as inquired/i)
  })

  it('US2 AS2 inquired job can be marked applied', async () => {
    const user = userEvent.setup()
    const calls = renderPage(detail({ state: 'inquired', inquired_on: '2026-11-03' }))

    expect(await screen.findByText(
      (_, el) => el?.textContent === 'Inquired on 3 Nov 2026' && el.tagName === 'SPAN',
    )).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'I inquired' })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'I applied' }))

    await waitFor(() =>
      expect(calls.some((c) => c.method === 'POST' && c.path === '/jobs/j1/applied')).toBe(true),
    )
  })

  it('US2 AS3 undo inquired', async () => {
    const user = userEvent.setup()
    const calls = renderPage()
    await user.click(await screen.findByRole('button', { name: 'I inquired' }))

    const notice = await screen.findByRole('status')
    await user.click(within(notice).getByRole('button', { name: 'Undo' }))

    await waitFor(() =>
      expect(calls.some((c) => c.method === 'DELETE' && c.path === '/jobs/j1/inquired')).toBe(true),
    )
    expect(calls.some((c) => c.method === 'DELETE' && c.path === '/jobs/j1/applied')).toBe(false)
  })

  it('an inquired job can be undone from its page', async () => {
    const user = userEvent.setup()
    const calls = renderPage(detail({ state: 'inquired', inquired_on: '2026-11-03' }))

    await user.click(await screen.findByRole('button', { name: 'Undo' }))

    await waitFor(() =>
      expect(calls.some((c) => c.method === 'DELETE' && c.path === '/jobs/j1/inquired')).toBe(true),
    )
  })

  it('FR007 no I inquired on an applied job', async () => {
    renderPage(detail({ state: 'applied', applied_on: '2026-11-03' }))

    await screen.findByText(
      (_, el) => el?.textContent === 'Applied on 3 Nov 2026' && el.tagName === 'SPAN',
    )

    expect(screen.queryByRole('button', { name: 'I inquired' })).not.toBeInTheDocument()
  })

  it('a skipped job can be marked inquired', async () => {
    renderPage(detail({ state: 'skipped' }))

    expect(await screen.findByRole('button', { name: 'I inquired' })).toBeInTheDocument()
  })

  it('US2 AS5 date error shown', async () => {
    const user = userEvent.setup()
    renderPage()

    await user.click(await screen.findByRole('button', { name: 'Pick a date' }))
    const date = screen.getByLabelText('Date')
    fireEvent.change(date, { target: { value: '2999-01-01' } })
    await user.click(screen.getByRole('button', { name: 'I inquired' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('The date cannot be in the future.')
  })
})


describe('JobDetailPage unsaved edits', () => {
  function renderInDataRouter() {
    stubApi((call) => {
      if (call.path === '/jobs/j1') return detail({ state: 'applied', applied_on: '2026-11-05' })
      if (call.path === '/jobs/j1/interview') {
        return {
          job_id: 'j1',
          can_edit: true,
          can_add_round: true,
          contact: null,
          source: null,
          rounds: [],
          status: { state: 'applied', round: null },
          resume: { state: 'none', resume_file_id: null, name: null, added_on: null },
        }
      }
      return undefined
    })
    const router = createMemoryRouter(
      [
        { path: '/jobs/:id', element: <JobDetailPage /> },
        { path: '/elsewhere', element: <p>Another page</p> },
      ],
      { initialEntries: ['/jobs/j1'] },
    )
    render(
      <QueryClientProvider client={new QueryClient()}>
        <RouterProvider router={router} />
      </QueryClientProvider>,
    )
    return router
  }

  afterEach(() => vi.unstubAllGlobals())

  it('FR013 leaving the page with unsaved edits asks first', async () => {
    const user = userEvent.setup()
    const router = renderInDataRouter()
    await user.type(await screen.findByLabelText('Contact name'), 'Asha')

    await act(async () => {
      await router.navigate('/elsewhere')
    })

    expect(screen.getByRole('alertdialog', { name: 'Unsaved changes' })).toBeInTheDocument()
    expect(screen.queryByText('Another page')).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Stay on this page' }))
    expect(screen.getByLabelText('Contact name')).toHaveValue('Asha')

    await act(async () => {
      await router.navigate('/elsewhere')
    })
    await user.click(screen.getByRole('button', { name: 'Leave and lose them' }))
    expect(await screen.findByText('Another page')).toBeInTheDocument()
  })

  it('FR013 no question when nothing changed', async () => {
    const router = renderInDataRouter()
    await screen.findByLabelText('Contact name')

    await act(async () => {
      await router.navigate('/elsewhere')
    })

    expect(await screen.findByText('Another page')).toBeInTheDocument()
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()
  })

  it('US1 AS2 an inquired job starts the resume choice on its own resume', async () => {
    const file = (id: string, name: string, at: string) => ({
      id,
      kind: 'upload_pdf',
      original_name: name,
      size_bytes: 1000,
      page_count: 1,
      parse_status: 'parsed',
      parse_result: null,
      created_at: at,
      has_open_review: false,
      open_review_id: null,
    })
    renderPage(
      detail({
        state: 'inquired',
        inquired_on: '2026-11-03',
        resume: { state: 'chosen', resume_file_id: 'f1', name: 'Own.pdf', added_on: '2025-03-14' },
      }),
      undefined,
      (call) => {
        if (call.path === '/resumes')
          return [
            file('f1', 'Own.pdf', '2025-03-14T09:00:00Z'),
            file('f2', 'Last.pdf', '2026-10-02T09:00:00Z'),
          ]
        if (call.path === '/pipeline/resumes') return { last_choice: 'f2', usage: [] }
        return undefined
      },
    )

    const select = await screen.findByRole('combobox', { name: 'Resume used' })

    expect(select).toHaveValue('f1') // not the last choice, f2
  })

  it('US2 AS3 the job page shows the resume name and the day it was added', async () => {
    renderPage(detail({ state: 'applied', applied_on: '2026-11-03' }), {
      job_id: 'j1',
      can_edit: true,
      can_add_round: true,
      contact: null,
      source: null,
      rounds: [],
      status: { state: 'applied', round: null },
      resume: { state: 'chosen', resume_file_id: 'f1', name: 'Own.pdf', added_on: '2025-03-14' },
    })

    expect(await screen.findByText('Own.pdf · added 14 Mar 2025')).toBeInTheDocument()
  })
})

