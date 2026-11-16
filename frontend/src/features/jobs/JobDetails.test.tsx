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

function renderDetails(actions?: boolean) {
  stubApi((call) => {
    if (call.path === '/jobs/j1') return detail()
    if (call.path === '/jobs/j1/interview') return undefined
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
})
