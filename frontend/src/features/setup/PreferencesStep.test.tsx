import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { StepCard } from './StepCard'
import { type Onboarding, useOnboarding } from './useOnboarding'

const json = (body: unknown, status = 200, type = 'application/json') =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': type } })

const defaults = {
  target_roles: [],
  seniority_levels: [],
  years_experience: null,
  key_skills: [],
  preferred_locations: [],
  default_country: 'IN',
  work_modes: ['hybrid', 'onsite', 'remote'],
  willing_to_relocate: false,
  blocked_locations: [],
  job_types: ['full_time'],
  pay: { currency: 'INR', min_annual: null, target_annual: null, basis: 'fixed' },
  notice_period_days: 30,
  earliest_start_date: null,
  preferred_companies: [],
  avoided_companies: [],
}

let calls: { method: string; url: string; body?: string }[]
let completeReply: () => Response

beforeEach(() => {
  calls = []
  completeReply = () => json({ setup_completed_at: '2026-11-04T09:00:00Z' })
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? 'GET'
      calls.push({ method, url, body: init?.body as string | undefined })
      if (url.endsWith('/onboarding/complete')) return completeReply()
      if (url.endsWith('/preferences') && method === 'PUT') {
        return json({ saved_at: '2026-11-04T09:00:00Z' })
      }
      if (url.endsWith('/preferences')) {
        return json({
          content: defaults,
          saved_at: null,
          suggestions: { target_roles: ['Backend Engineer'], key_skills: [] },
        })
      }
      if (url.endsWith('/onboarding')) {
        return json({ step: 4, display_name: 'Jane', open_review_id: null, active_run_id: null })
      }
      return json([])
    }),
  )
})
afterEach(() => vi.unstubAllGlobals())

function GateProbe() {
  useOnboarding()
  return null
}

function renderStep() {
  const data: Onboarding = {
    step: 4,
    display_name: 'Jane',
    open_review_id: null,
    active_run_id: null,
  }
  return render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <MemoryRouter>
        <GateProbe />
        <StepCard onboarding={data} />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('PreferencesStep', () => {
  it('shows_the_card_heading_and_the_finish_button', async () => {
    renderStep()
    expect(
      await screen.findByRole('heading', { name: 'What are you looking for?' }),
    ).toBeInTheDocument()
    expect(await screen.findByRole('button', { name: 'Finish setup' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Save preferences' })).not.toBeInTheDocument()
    expect(screen.queryByRole('heading', { level: 1, name: 'Preferences' })).not.toBeInTheDocument()
  })

  it('US5_AS7_finish_setup_opens_home', async () => {
    const user = userEvent.setup()
    renderStep()
    await user.click(await screen.findByRole('button', { name: "Add 'Backend Engineer'" }))
    const reads = () =>
      calls.filter((c) => c.url.endsWith('/onboarding') && c.method === 'GET').length
    const before = reads()

    await user.click(screen.getByRole('button', { name: 'Finish setup' }))

    await waitFor(() =>
      expect(calls.some((c) => c.url.endsWith('/onboarding/complete'))).toBe(true),
    )
    const order = calls.filter((c) => c.method !== 'GET').map((c) => c.url.split('/api/v1')[1])
    expect(order).toEqual(['/preferences', '/onboarding/complete']) // saved first, then finished
    await waitFor(() => expect(reads()).toBeGreaterThan(before)) // the gate re-reads and opens Home
  })

  it('finish_is_refused_until_the_form_is_valid', async () => {
    const user = userEvent.setup()
    renderStep()
    await user.click(await screen.findByRole('button', { name: 'Finish setup' }))
    expect(await screen.findByText('Add at least one target role')).toBeInTheDocument()
    expect(calls.some((c) => c.method === 'PUT')).toBe(false)
    expect(calls.some((c) => c.url.endsWith('/onboarding/complete'))).toBe(false)
  })

  it('shows_why_finishing_failed', async () => {
    completeReply = () =>
      json(
        {
          title: 'Conflict',
          status: 409,
          detail: 'Confirm your profile and save your preferences first',
        },
        409,
        'application/problem+json',
      )
    const user = userEvent.setup()
    renderStep()
    await user.click(await screen.findByRole('button', { name: "Add 'Backend Engineer'" }))
    await user.click(screen.getByRole('button', { name: 'Finish setup' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Confirm your profile')
  })
})
