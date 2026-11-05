import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { PreferencesPage } from './PreferencesPage'

const json = (body: unknown, status = 200, type = 'application/json') =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': type } })

function defaults(overrides: Record<string, unknown> = {}) {
  return {
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
    ...overrides,
  }
}

type Reply = { content?: object; saved_at?: string | null; suggestions?: object }
let calls: { method: string; body?: string }[]
let put: () => Response

function serve(reply: Reply = {}) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (_url: string, init?: RequestInit) => {
      const method = init?.method ?? 'GET'
      calls.push({ method, body: init?.body as string | undefined })
      if (method === 'PUT') return put()
      return json({
        content: reply.content ?? defaults(),
        saved_at: reply.saved_at ?? null,
        suggestions: reply.suggestions ?? { target_roles: [], key_skills: [] },
      })
    }),
  )
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <PreferencesPage />
    </QueryClientProvider>,
  )
}

const sent = () => {
  const call = calls.find((c) => c.method === 'PUT')
  if (!call?.body) throw new Error('nothing was saved')
  return JSON.parse(call.body) as Record<string, unknown> & { pay?: object; job_types: string[] }
}

beforeEach(() => {
  calls = []
  put = () => json({ saved_at: '2026-11-04T09:00:00Z' })
})
afterEach(() => vi.unstubAllGlobals())

describe('PreferencesPage', () => {
  it('US2_AS1_shows_defaults', async () => {
    serve()
    renderPage()

    expect(await screen.findByLabelText('Default country')).toHaveValue('IN')
    expect(screen.getByLabelText('Notice period (days)')).toHaveValue(30)
    for (const mode of ['On-site', 'Hybrid', 'Remote']) {
      expect(screen.getByRole('checkbox', { name: mode })).toBeChecked()
    }
    expect(screen.getByRole('checkbox', { name: 'Full-time' })).toBeChecked()
    expect(screen.getByRole('checkbox', { name: 'Contract' })).not.toBeChecked()
    expect(screen.getByLabelText('Currency')).toHaveValue('INR')
    expect(screen.getByText('Not saved yet')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^Remove/ })).not.toBeInTheDocument()
  })

  it('US2_AS3_suggestion_added_only_on_click', async () => {
    serve({ suggestions: { target_roles: ['Backend Engineer'], key_skills: ['Python'] } })
    const user = userEvent.setup()
    renderPage()

    const suggestion = await screen.findByRole('button', { name: "Add 'Backend Engineer'" })
    expect(screen.queryByRole('button', { name: 'Remove Backend Engineer' })).not.toBeInTheDocument()
    expect(calls.some((c) => c.method === 'PUT')).toBe(false)

    await user.click(suggestion)

    expect(screen.getByRole('button', { name: 'Remove Backend Engineer' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: "Add 'Backend Engineer'" })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: "Add 'Python'" })).toBeInTheDocument()
  })

  it('US2_AS4_errors_next_to_fields', async () => {
    serve()
    const user = userEvent.setup()
    renderPage()
    await screen.findByLabelText('Default country')

    await user.click(screen.getByRole('button', { name: 'Save preferences' }))

    const roles = screen.getByTestId('field-target_roles')
    expect(await within(roles).findByRole('alert')).toHaveTextContent('Add at least one target role')
    expect(calls.some((c) => c.method === 'PUT')).toBe(false)
  })

  it('US2_AS4_server_errors_are_shown_on_their_field', async () => {
    serve()
    put = () =>
      json(
        {
          title: 'Some fields are not valid.',
          status: 422,
          errors: [{ field: 'pay.min_annual', message: 'Minimum pay cannot be above the target' }],
        },
        422,
        'application/problem+json',
      )
    const user = userEvent.setup()
    renderPage()
    await user.type(await screen.findByLabelText('Target roles'), 'Data Engineer{Enter}')

    await user.click(screen.getByRole('button', { name: 'Save preferences' }))

    const pay = screen.getByTestId('field-min_pay')
    expect(await within(pay).findByRole('alert')).toHaveTextContent(
      'Minimum pay cannot be above the target',
    )
  })

  it('saves_what_was_typed_and_shows_last_saved', async () => {
    serve()
    const user = userEvent.setup()
    renderPage()
    await user.type(await screen.findByLabelText('Target roles'), 'Data Engineer{Enter}')
    await user.type(screen.getByLabelText('Key skills'), 'SQL,')
    await user.type(screen.getByLabelText('Years of experience'), '6.5')
    await user.click(screen.getByRole('checkbox', { name: 'Contract' }))

    await user.click(screen.getByRole('button', { name: 'Save preferences' }))

    await waitFor(() => expect(screen.getByText(/Last saved/)).toBeInTheDocument())
    const body = sent()
    expect(body.target_roles).toEqual(['Data Engineer'])
    expect(body.key_skills).toEqual(['SQL'])
    expect(body.years_experience).toBe('6.5')
    expect([...body.job_types].sort()).toEqual(['contract', 'full_time'])
    expect(body.notice_period_days).toBe(30)
    expect(body.earliest_start_date).toBeNull()
  })

  it('US2_AS5_inr_shows_lpa', async () => {
    serve({
      content: defaults({
        target_roles: ['Data Engineer'],
        pay: { currency: 'INR', min_annual: '1850000', target_annual: '2400000', basis: 'fixed' },
      }),
      saved_at: '2026-11-04T09:00:00Z',
    })
    const user = userEvent.setup()
    renderPage()

    const min = await screen.findByLabelText('Minimum pay (LPA)')
    expect(min).toHaveValue('18.5')
    expect(screen.getByLabelText('Target pay (LPA)')).toHaveValue('24')

    await user.clear(screen.getByLabelText('Target pay (LPA)'))
    await user.type(screen.getByLabelText('Target pay (LPA)'), '30')
    await user.click(screen.getByRole('button', { name: 'Save preferences' }))
    await waitFor(() => expect(calls.some((c) => c.method === 'PUT')).toBe(true))
    expect(sent().pay).toMatchObject({ currency: 'INR', min_annual: '1850000', target_annual: '3000000' })

    await user.selectOptions(screen.getByLabelText('Currency'), 'USD')
    expect(screen.getByLabelText('Minimum pay (per year)')).toBeInTheDocument()
    expect(screen.queryByLabelText('Minimum pay (LPA)')).not.toBeInTheDocument()
  })
})
