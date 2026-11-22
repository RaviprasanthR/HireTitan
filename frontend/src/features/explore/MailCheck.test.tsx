import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { type Call, problem, stubApi } from '@/test/api'
import { RunSummaryPage } from './RunSummaryPage'
import { SearchPanel } from './SearchPanel'

function mailRun(over: Record<string, unknown> = {}, mail: Record<string, unknown> = {}) {
  return {
    id: 'm1',
    run_id: 'w1',
    mode: 'mail_alerts',
    outcome: null,
    stop_message: null,
    stop_requested: false,
    batches_done: 1,
    companies_total: 0,
    companies_read: 0,
    jobs_found: 9,
    skipped_by_rules: 2,
    judged_by_ai: 0,
    kept: 0,
    added: 5,
    merged: 2,
    not_checked_by_ai: 5,
    ai_note: null,
    started_at: '2026-11-18T09:00:00Z',
    finished_at: null,
    mail: {
      trigger: 'button',
      window_start: '2026-11-17T09:00:00Z',
      emails_listed: 12,
      emails_skipped: 3,
      emails_read: 4,
      emails_unreadable: 1,
      more_remaining: false,
      ended: null,
      unreadable: [],
      already_in_pipeline: [],
      ...mail,
    },
    ...over,
  }
}

const CONNECTED = {
  state: 'connected',
  address: 'jobseeker@example.invalid',
  credentials_set: true,
  credentials_from_environment: false,
  redirect_uri: 'http://localhost:8000/api/v1/mail/google/callback',
  last_check_started_at: null,
  last_error: null,
  window_hours: 24,
}

function renderPanel(
  latest: unknown,
  connection: unknown = CONNECTED,
  extra?: (c: Call) => unknown,
) {
  const calls = stubApi((call) => {
    const custom = extra?.(call)
    if (custom !== undefined) return custom
    if (call.path === '/search/latest') return latest
    if (call.path === '/mail/connection') return connection
    if (call.path === '/mail/checks' && call.method === 'POST')
      return new Response('{"search_run_id":"m2"}', {
        status: 202,
        headers: { 'Content-Type': 'application/json' },
      })
    if (call.path.endsWith('/stop'))
      return new Response('{"stopping":true}', {
        status: 202,
        headers: { 'Content-Type': 'application/json' },
      })
    return undefined
  })
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <MemoryRouter>
        <SearchPanel />
      </MemoryRouter>
    </QueryClientProvider>,
  )
  return calls
}

afterEach(() => vi.unstubAllGlobals())

describe('SearchPanel: job-alert mail', () => {
  it('US2 check job-alert mail button starts a check', async () => {
    const user = userEvent.setup()
    const calls = renderPanel(null)

    await user.click(await screen.findByRole('button', { name: 'Check job-alert mail' }))

    await waitFor(() =>
      expect(calls.some((c) => c.method === 'POST' && c.path === '/mail/checks')).toBe(true),
    )
  })

  it('US2 there is no check button when Gmail is not connected', async () => {
    renderPanel(null, { ...CONNECTED, state: 'not_connected', address: null })

    await screen.findByRole('button', { name: 'Search now' })

    expect(screen.queryByRole('button', { name: 'Check job-alert mail' })).not.toBeInTheDocument()
  })

  it('US2 there is no check button when Gmail access has ended', async () => {
    renderPanel(null, { ...CONNECTED, state: 'needs_reconnect' })

    await screen.findByRole('button', { name: 'Search now' })

    expect(screen.queryByRole('button', { name: 'Check job-alert mail' })).not.toBeInTheDocument()
  })

  it('US2 a refused check says why', async () => {
    const user = userEvent.setup()
    renderPanel(null, CONNECTED, (call) =>
      call.path === '/mail/checks'
        ? problem(409, 'Conflict', {
            detail: 'A search is already running.',
            reason: 'search_running',
          })
        : undefined,
    )

    await user.click(await screen.findByRole('button', { name: 'Check job-alert mail' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('A search is already running.')
  })

  it('US2 AS7 progress and stop', async () => {
    const user = userEvent.setup()
    const calls = renderPanel(mailRun())

    await waitFor(() =>
      expect(screen.getByRole('status')).toHaveTextContent('Reading your job-alert mail…'),
    )
    expect(
      screen.getByText(/Read 4 of 9 new emails \(1 could not be read\) · 5 new jobs so far/),
    ).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Stop' }))

    await waitFor(() =>
      expect(calls.some((c) => c.method === 'POST' && c.path === '/search/runs/m1/stop')).toBe(
        true,
      ),
    )
    expect(screen.queryByRole('button', { name: 'Check job-alert mail' })).not.toBeInTheDocument()
  })

  it('US2 a finished mail check says so and shows the mail flow', async () => {
    renderPanel(
      mailRun(
        { outcome: 'finished', finished_at: '2026-11-18T09:02:00Z' },
        { ended: 'finished', emails_read: 8, emails_unreadable: 1 },
      ),
    )

    await waitFor(() =>
      expect(screen.getByRole('status')).toHaveTextContent('Mail check finished.'),
    )
    const flow = await screen.findByRole('list', { name: /how the mail check went/i })
    expect(within(flow).getByText('Emails read')).toBeInTheDocument()
  })

  it('US2 a mail check that could not reach Gmail says so', async () => {
    renderPanel(
      mailRun(
        {
          outcome: 'failed',
          stop_message: 'Gmail did not answer.',
          finished_at: '2026-11-18T09:02:00Z',
        },
        { ended: 'gmail_unavailable' },
      ),
    )

    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('Mail check stopped'))
    expect(screen.getByText('Gmail did not answer.')).toBeInTheDocument()
  })
})

describe('SearchPanel: mail and company search together', () => {
  it('a company search started after a mail check says it is searching companies', async () => {
    const user = userEvent.setup()
    renderPanel(
      mailRun({ outcome: 'finished', finished_at: '2026-11-18T09:02:00Z' }, { ended: 'finished' }),
      CONNECTED,
      (call) =>
        call.path === '/search/runs' && call.method === 'POST'
          ? new Promise(() => {}) // the server has not answered yet
          : undefined,
    )

    await user.click(await screen.findByRole('button', { name: 'Search now' }))

    await waitFor(() =>
      expect(screen.getByRole('status')).toHaveTextContent('Searching your companies…'),
    )
  })

  it('the progress line says how many emails could not be read', async () => {
    renderPanel(mailRun({}, { emails_read: 4, emails_unreadable: 2 }))

    expect(await screen.findByText(/Read 4 of 9 new emails/)).toHaveTextContent(
      '2 could not be read',
    )
  })

  it('a check that ended because Gmail access ended points to Settings', async () => {
    renderPanel(
      mailRun(
        {
          outcome: 'failed',
          stop_message: 'Gmail access has ended.',
          finished_at: '2026-11-18T09:02:00Z',
        },
        { ended: 'access_ended' },
      ),
    )

    expect(await screen.findByRole('link', { name: /settings/i })).toHaveAttribute(
      'href',
      '/settings',
    )
  })
})

function renderSummary(run: unknown, skipped: unknown = { items: [], next_cursor: null }) {
  stubApi((call) => {
    if (call.path === '/search/runs/m1') return { companies: [], ...(run as object) }
    if (call.path.startsWith('/search/runs/m1/skipped')) return skipped
    return undefined
  })
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <MemoryRouter initialEntries={['/search/runs/m1']}>
        <Routes>
          <Route path="/search/runs/:id" element={<RunSummaryPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('RunSummaryPage: mail run', () => {
  const finished = mailRun(
    { outcome: 'finished', finished_at: '2026-11-18T09:02:00Z' },
    {
      ended: 'finished',
      emails_read: 8,
      emails_unreadable: 1,
      unreadable: [
        {
          sender: 'naukrialerts@naukri.com',
          received_at: '2026-11-18T05:00:00Z',
          why: 'unreadable',
        },
        {
          sender: 'weekly@digest.example.invalid',
          received_at: '2026-11-18T06:00:00Z',
          why: 'needs_ai',
        },
      ],
    },
  )

  it('US2 mail run shows emails read → jobs found → rules → new jobs and could-not-read list', async () => {
    const user = userEvent.setup()
    renderSummary(finished)

    expect(await screen.findByRole('heading', { name: 'Mail check summary' })).toBeInTheDocument()
    const flow = screen.getByRole('list', { name: /how the mail check went/i })
    expect(within(flow).getByText('Emails read')).toBeInTheDocument()
    expect(within(flow).getByText('8 of 9')).toBeInTheDocument()
    expect(within(flow).getByText('Jobs found')).toBeInTheDocument()
    expect(within(flow).getByText('Your rules')).toBeInTheDocument()
    expect(within(flow).getByText('New jobs')).toBeInTheDocument()
    expect(screen.queryByText(/Companies read/)).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Show details' }))
    const list = screen.getByRole('list', { name: /could not be read/i })
    expect(within(list).getByText(/naukrialerts@naukri\.com/)).toBeInTheDocument()
    expect(within(list).getByText(/layout HireTitan does not know/i)).toBeInTheDocument()
    expect(within(list).getByText(/waiting for the AI/i)).toBeInTheDocument()
    expect(screen.queryByText(/Companies to check by hand/)).not.toBeInTheDocument()
  })

  it('US3 AS4 jobs already in the pipeline are listed, not shown again', async () => {
    const user = userEvent.setup()
    renderSummary(
      mailRun(
        { outcome: 'finished', finished_at: '2026-11-18T09:02:00Z' },
        {
          ended: 'finished',
          already_in_pipeline: [{ job_id: 'j7', title: 'Data Engineer', company: 'Granite Tech' }],
        },
      ),
    )

    await user.click(await screen.findByRole('button', { name: 'Show details' }))

    const list = screen.getByRole('list', { name: /already in your pipeline/i })
    const link = within(list).getByRole('link', { name: 'Data Engineer' })
    expect(link).toHaveAttribute('href', '/jobs/j7')
    expect(within(list).getByText(/Granite Tech/)).toBeInTheDocument()
  })

  it('US2 the left-out jobs of a mail check can be restored', async () => {
    const user = userEvent.setup()
    renderSummary(finished, {
      items: [
        {
          id: 'j9',
          title: 'Marketing Manager',
          company_name: 'Acme',
          state: 'skipped',
          decision: {
            outcome: 'skipped',
            decided_by: 'rule',
            reason: 'title matches none of your roles',
          },
        },
      ],
      next_cursor: null,
    })

    await user.click(await screen.findByRole('button', { name: 'Show details' }))
    await user.click(screen.getByText(/Jobs left out/))

    expect(await screen.findByRole('button', { name: 'Restore' })).toBeInTheDocument()
  })

  it('US5 a check that found no mail says so and points to the sender list', async () => {
    renderSummary(
      mailRun(
        { outcome: 'finished', finished_at: '2026-11-18T09:02:00Z', jobs_found: 0, added: 0 },
        { ended: 'finished', emails_listed: 0, emails_skipped: 0, emails_read: 0 },
      ),
    )

    const note = await screen.findByRole('status', { name: 'Mail check result' })
    expect(note).toHaveTextContent('Gmail returned no mail from your job sites')
    expect(note).toHaveTextContent('last 24 hours')
    expect(within(note).getByRole('link', { name: /sender list/i })).toHaveAttribute(
      'href',
      '/settings',
    )
  })

  it('US5 a check whose mail was all read before says so', async () => {
    renderSummary(
      mailRun(
        { outcome: 'finished', finished_at: '2026-11-18T09:02:00Z', jobs_found: 0, added: 0 },
        { ended: 'finished', emails_listed: 4, emails_skipped: 4, emails_read: 0 },
      ),
    )

    expect(await screen.findByRole('status', { name: 'Mail check result' })).toHaveTextContent(
      'All 4 emails were already read by an earlier check.',
    )
  })

  it('US5 a check that read mail but found no jobs in it says so', async () => {
    renderSummary(
      mailRun(
        { outcome: 'finished', finished_at: '2026-11-18T09:02:00Z', jobs_found: 0, added: 0 },
        { ended: 'finished', emails_listed: 5, emails_skipped: 0, emails_read: 5 },
      ),
    )

    expect(await screen.findByRole('status', { name: 'Mail check result' })).toHaveTextContent(
      '5 emails were looked at, but none held a job alert HireTitan could read.',
    )
  })

  it('US5 no note when the check found jobs', async () => {
    renderSummary(
      mailRun(
        { outcome: 'finished', finished_at: '2026-11-18T09:02:00Z' },
        { ended: 'finished', emails_listed: 4, emails_skipped: 0, emails_read: 4 },
      ),
    )

    await screen.findByRole('heading', { name: 'Mail check summary' })
    expect(screen.queryByRole('status', { name: 'Mail check result' })).not.toBeInTheDocument()
  })

  it('US5 no note while the check is still running or when it ended early', async () => {
    renderSummary(
      mailRun(
        { outcome: 'failed', stop_message: 'Gmail did not answer.', finished_at: '2026-11-18T09:02:00Z', jobs_found: 0 },
        { ended: 'gmail_unavailable', emails_listed: 0 },
      ),
    )

    await screen.findByRole('heading', { name: 'Mail check summary' })
    expect(screen.queryByRole('status', { name: 'Mail check result' })).not.toBeInTheDocument()
  })

  it('FR012 says when there were more emails than one check reads', async () => {
    renderSummary(
      mailRun(
        { outcome: 'finished', finished_at: '2026-11-18T09:02:00Z' },
        { ended: 'finished', more_remaining: true },
      ),
    )

    expect(await screen.findByText(/more mail than one check reads/i)).toBeInTheDocument()
  })

  it('FR005 says when Gmail access ended during the check', async () => {
    renderSummary(
      mailRun(
        {
          outcome: 'failed',
          stop_message: 'Gmail access has ended.',
          finished_at: '2026-11-18T09:02:00Z',
        },
        { ended: 'access_ended' },
      ),
    )

    expect(await screen.findByText('Gmail access has ended.')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /settings/i })).toHaveAttribute('href', '/settings')
  })

  it('a company search keeps its own summary', async () => {
    renderSummary({
      ...mailRun({
        mode: 'rules_and_ai',
        outcome: 'finished',
        companies_total: 3,
        companies_read: 3,
      }),
      mail: null,
      companies: [],
    })

    expect(await screen.findByRole('heading', { name: 'Search summary' })).toBeInTheDocument()
  })
})
