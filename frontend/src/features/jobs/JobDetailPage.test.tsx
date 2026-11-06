import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { stubApi } from '@/test/api'
import { JobDetailPage } from './JobDetailPage'
import { UndoToast } from './UndoToast'

function detail(over: Record<string, unknown> = {}) {
  return {
    id: 'j1',
    title: 'Backend Engineer',
    company_name: 'Acme',
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
            applied_on: (call.body as { applied_on?: string } | undefined)?.applied_on ?? '2026-11-06',
          }
    if (call.path === '/jobs/j1') return job
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
    await user.click(screen.getByRole('button', { name: 'Save' }))

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

    await user.click(await screen.findByRole('button', { name: 'I applied' }))
    const date = screen.getByLabelText('Date applied')
    await user.clear(date)
    await user.type(date, '2026-11-03')
    await user.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() =>
      expect(
        calls.find((c) => c.method === 'POST' && c.path === '/jobs/j1/applied')?.body,
      ).toEqual({ applied_on: '2026-11-03' }),
    )
  })

  it('US5_AS3_undo_from_the_notice', async () => {
    const user = userEvent.setup()
    const calls = renderPage()
    await user.click(await screen.findByRole('button', { name: 'I applied' }))
    await user.click(screen.getByRole('button', { name: 'Save' }))

    const notice = await screen.findByRole('status')
    await user.click(within(notice).getByRole('button', { name: 'Undo' }))

    await waitFor(() =>
      expect(calls.some((c) => c.method === 'DELETE' && c.path === '/jobs/j1/applied')).toBe(true),
    )
  })

  it('US5_AS4_pasted_job_can_be_marked_applied', async () => {
    renderPage(
      detail({
        sources: [{ kind: 'manual', url: 'https://jobs.example.com/pasted' }],
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
})
