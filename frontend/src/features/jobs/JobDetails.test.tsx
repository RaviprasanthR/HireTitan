import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { stubApi } from '@/test/api'
import { JobDetails } from './JobDetails'

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
    sources: [{ kind: 'company_board', url: 'https://jobs.example.com/acme/1' }],
    decision: { outcome: 'shown', decided_by: 'rules_only_fallback', reason: 'not checked by AI' },
    listed: true,
    applied_on: null,
    inquired_on: null,
    description: 'Build APIs with Python.',
    city: 'Pune',
    country: 'IN',
    skills_found: [],
    years_found: null,
    canonical_url: 'https://jobs.example.com/acme/1',
    injection_flags: [],
    decision_history: [],
    first_search_id: null,
    ...over,
  }
}

function renderDetails(
  actions?: boolean,
  jobOver: Record<string, unknown> = {},
  interview?: unknown,
) {
  stubApi((call) => {
    if (call.path === '/jobs/j1') return detail(jobOver)
    if (call.path === '/jobs/j1/interview') return interview
    if (call.path === '/pipeline/resumes') return { last_choice: null, usage: [] }
    if (call.path === '/resumes') return []
    return undefined
  })
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <MemoryRouter>
        <JobDetails id="j1" actions={actions} />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

afterEach(() => vi.unstubAllGlobals())

describe('JobDetails', () => {
  it('renders_the_description_the_reason_and_the_sources', async () => {
    renderDetails()

    expect(await screen.findByText('Build APIs with Python.')).toBeInTheDocument()
    expect(screen.getByText('Why it is listed')).toBeInTheDocument()
    expect(screen.getByRole('list', { name: 'Sources' })).toHaveTextContent(
      'https://jobs.example.com/acme/1',
    )
    expect(screen.getByRole('link', { name: 'Open original posting' })).toHaveAttribute(
      'href',
      'https://jobs.example.com/acme/1',
    )
  })

  it('has_the_actions_by_default', async () => {
    renderDetails()
    expect(await screen.findByRole('button', { name: 'Check again' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /I applied/i })).toBeInTheDocument()
  })

  it('FR025_leaves_out_the_buttons_when_the_surrounding_row_has_them', async () => {
    renderDetails(false)
    await screen.findByText('Build APIs with Python.')
    expect(screen.queryByRole('button', { name: 'Check again' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /I applied/i })).not.toBeInTheDocument()
  })

  it('FR025_an_applied_job_in_a_row_shows_its_interview_details_for_reading_only', async () => {
    const interview = {
      job_id: 'j1',
      can_edit: true,
      can_add_round: true,
      contact: { name: 'Asha Rao', role: null, email: null, phone: null, linkedin_url: null },
      source: { kind: 'direct', firm_name: null },
      rounds: [],
      status: { state: 'applied', round: null },
      resume: { state: 'none', resume_file_id: null, name: null, added_on: null },
    }
    renderDetails(false, { state: 'applied', applied_on: '2026-11-06' }, interview)

    const name = await screen.findByLabelText('Contact name')
    expect(name).toHaveValue('Asha Rao')
    // shown to read, not to change: editing happens on the job page, which asks before leaving
    expect(name).toBeDisabled()
    expect(screen.queryByRole('button', { name: /save/i })).not.toBeInTheDocument()
  })

  it('FR027_the_details_are_a_labelled_group', async () => {
    renderDetails(false)
    expect(
      await screen.findByRole('group', { name: 'Details of Backend Engineer' }),
    ).toBeInTheDocument()
  })
})
