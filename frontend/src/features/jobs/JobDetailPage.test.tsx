import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { problem, stubApi } from '@/test/api'
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

function renderPage(job = detail()) {
  const calls = stubApi((call) => {
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
    const original = screen.getByRole('link', { name: 'Open original posting' })
    expect(original).toHaveAttribute('href', 'https://jobs.example.com/acme/1')
    expect(original).toHaveAttribute('rel', expect.stringContaining('noopener'))
    const sources = screen.getByRole('list', { name: 'Sources' })
    expect(within(sources).getAllByRole('link')).toHaveLength(2)
    expect(screen.getByRole('link', { name: /first found/i })).toHaveAttribute(
      'href',
      '/search/runs/s1',
    )
    const history = screen.getByRole('list', { name: 'Decision history' })
    expect(within(history).getAllByRole('listitem')).toHaveLength(2)
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

    await user.click(await screen.findByRole('button', { name: /check again/i }))

    await waitFor(() => expect(calls.some((c) => c.path === '/jobs/j1/recheck')).toBe(true))
  })

  it('does_not_unwrap_the_original_link_when_there_is_none', async () => {
    renderPage(detail({ canonical_url: null, sources: [] }))
    await screen.findByRole('heading', { level: 1, name: 'Backend Engineer' })
    expect(screen.queryByRole('link', { name: 'Open original posting' })).not.toBeInTheDocument()
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

    await user.click(await screen.findByRole('button', { name: 'Other date' }))
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

    expect(await screen.findByText('Applied on 3 Nov 2026')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Undo' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'I applied' })).not.toBeInTheDocument()
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

    expect(await screen.findByText('Inquired on 3 Nov 2026')).toBeInTheDocument()
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

    await screen.findByText('Applied on 3 Nov 2026')

    expect(screen.queryByRole('button', { name: 'I inquired' })).not.toBeInTheDocument()
  })

  it('a skipped job can be marked inquired', async () => {
    renderPage(detail({ state: 'skipped' }))

    expect(await screen.findByRole('button', { name: 'I inquired' })).toBeInTheDocument()
  })

  it('US2 AS5 date error shown', async () => {
    const user = userEvent.setup()
    renderPage()

    await user.click(await screen.findByRole('button', { name: 'Other date' }))
    const date = screen.getByLabelText('Date')
    fireEvent.change(date, { target: { value: '2999-01-01' } })
    await user.click(screen.getByRole('button', { name: 'I inquired' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('The date cannot be in the future.')
  })
})
