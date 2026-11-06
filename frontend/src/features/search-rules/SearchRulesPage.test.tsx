import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { SearchRulesPage } from './SearchRulesPage'

const json = (body: unknown, status = 200, type = 'application/json') =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': type } })

type Item = { text: string; origin: string; effect: string }

function rules(overrides: Record<string, unknown> = {}) {
  return {
    title_words: [
      { text: 'Backend Engineer', origin: 'preference:target_roles[0]', effect: 'skips' },
      { text: 'backend developer', origin: 'synonym_table', effect: 'skips' },
    ] as Item[],
    title_avoid: [] as Item[],
    blocked_locations: [
      { city: 'Pune', country: 'IN', origin: 'preference:blocked_locations[0]', effect: 'skips' },
    ],
    max_age_days: 30,
    stack_keywords: [
      { text: 'Python', origin: 'profile:skills', effect: 'guides_ai' },
    ] as Item[],
    preferred_locations: [],
    work_modes: ['remote'],
    seniority: [],
    years_experience: null,
    ...overrides,
  }
}

function ruleSet(status: 'proposed' | 'approved', over: Record<string, unknown> = {}) {
  return {
    id: status === 'proposed' ? 'p1' : 'a1',
    version: status === 'proposed' ? 2 : 1,
    status,
    rules: rules(),
    based_on: {},
    approved_at: status === 'approved' ? '2026-11-05T10:00:00Z' : null,
    ...over,
  }
}

type State = { approved: unknown; proposal: unknown; stale: boolean }
let state: State
let calls: { method: string; path: string; body?: string }[]
let reply: (method: string, path: string) => Response | undefined

function serve() {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? 'GET'
      const path = url.replace('/api/v1', '')
      calls.push({ method, path, body: init?.body as string | undefined })
      const custom = reply(method, path)
      if (custom) return custom
      if (method === 'GET') return json(state)
      if (path.endsWith('/approve')) {
        state = { approved: ruleSet('approved'), proposal: null, stale: false }
        return json(ruleSet('approved'))
      }
      if (method === 'POST') {
        state = { ...state, proposal: ruleSet('proposed') }
        return json(ruleSet('proposed'), 201)
      }
      if (method === 'PUT') return json(ruleSet('proposed'))
      return new Response(null, { status: 204 })
    }),
  )
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <SearchRulesPage />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  state = { approved: null, proposal: ruleSet('proposed'), stale: false }
  calls = []
  reply = () => undefined
  serve()
})
afterEach(() => vi.unstubAllGlobals())

describe('SearchRulesPage', () => {
  it('US2_AS1_shows_origin_and_effect', async () => {
    renderPage()

    const roles = await screen.findByRole('region', { name: /job titles/i })
    const first = within(roles).getByText('Backend Engineer').closest('li') as HTMLElement
    expect(within(first).getByText(/from your preferences/i)).toBeInTheDocument()
    expect(within(first).getByText(/skips jobs/i)).toBeInTheDocument()
    const synonym = within(roles).getByText('backend developer').closest('li') as HTMLElement
    expect(within(synonym).getByText(/similar title/i)).toBeInTheDocument()

    const skills = screen.getByRole('region', { name: /skills/i })
    const python = within(skills).getByText('Python').closest('li') as HTMLElement
    expect(within(python).getByText(/from your profile/i)).toBeInTheDocument()
    expect(within(python).getByText(/guides the ai/i)).toBeInTheDocument()
  })

  it('US2_AS2_edit_then_approve', async () => {
    const user = userEvent.setup()
    renderPage()

    await user.type(await screen.findByLabelText(/add a word to avoid/i), 'manager')
    await user.click(screen.getByRole('button', { name: /add avoid word/i }))
    await user.click(screen.getByRole('button', { name: /approve/i }))

    await waitFor(() => expect(calls.some((c) => c.path.endsWith('/approve'))).toBe(true))
    const put = calls.findIndex((c) => c.method === 'PUT')
    const approve = calls.findIndex((c) => c.path.endsWith('/approve'))
    expect(put).toBeGreaterThan(-1)
    expect(put).toBeLessThan(approve)
    const sent = JSON.parse(calls[put]?.body as string)
    expect(sent.title_avoid).toEqual([{ text: 'manager', origin: 'user' }])
    expect(await screen.findByText(/rules approved/i)).toBeInTheDocument()
  })

  it('US2_AS4_stale_notice_offers_new_proposal', async () => {
    const user = userEvent.setup()
    state = { approved: ruleSet('approved'), proposal: null, stale: true }
    renderPage()

    expect(await screen.findByText(/your profile or preferences changed/i)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /propose new rules/i }))

    await waitFor(() =>
      expect(calls.some((c) => c.method === 'POST' && c.path === '/search/rules/proposal')).toBe(true),
    )
    expect(await screen.findByRole('button', { name: /approve/i })).toBeInTheDocument()
  })

  it('FR002_limit_errors_shown', async () => {
    const user = userEvent.setup()
    reply = (method) =>
      method === 'PUT'
        ? json(
            {
              status: 422,
              detail: 'Some fields are not valid.',
              errors: [{ field: 'title_words', message: 'Add at least 1.' }],
            },
            422,
            'application/problem+json',
          )
        : undefined
    renderPage()

    await screen.findByRole('region', { name: /job titles/i })
    for (const remove of screen.getAllByRole('button', { name: /remove (backend engineer|backend developer)/i })) {
      await user.click(remove)
    }
    await user.click(screen.getByRole('button', { name: /approve/i }))

    const roles = screen.getByRole('region', { name: /job titles/i })
    expect(await within(roles).findByRole('alert')).toHaveTextContent('Add at least 1.')
    expect(calls.some((c) => c.path.endsWith('/approve'))).toBe(false)
  })

  it('offers a first proposal when there are no rules yet', async () => {
    state = { approved: null, proposal: null, stale: false }
    const user = userEvent.setup()
    renderPage()

    await user.click(await screen.findByRole('button', { name: /propose rules/i }))

    expect(await screen.findByRole('button', { name: /approve/i })).toBeInTheDocument()
  })

  it('shows why a proposal cannot be made yet', async () => {
    state = { approved: null, proposal: null, stale: false }
    reply = (method) =>
      method === 'POST'
        ? json(
            { status: 409, detail: 'Confirm your profile first.', reason: 'no_confirmed_profile' },
            409,
            'application/problem+json',
          )
        : undefined
    const user = userEvent.setup()
    renderPage()

    await user.click(await screen.findByRole('button', { name: /propose rules/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Confirm your profile first.')
  })

  it('discard removes the proposal and keeps the approved rules', async () => {
    const user = userEvent.setup()
    state = { approved: ruleSet('approved'), proposal: ruleSet('proposed'), stale: false }
    renderPage()

    await user.click(await screen.findByRole('button', { name: /discard/i }))

    await waitFor(() => expect(calls.some((c) => c.method === 'DELETE')).toBe(true))
  })
})
