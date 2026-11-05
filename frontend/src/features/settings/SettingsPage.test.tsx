import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { SettingsPage } from './SettingsPage'

const json = (body: unknown, status = 200, type = 'application/json') =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': type } })

function settings(overrides: Record<string, unknown> = {}) {
  return {
    budget_cap_usd: '25.00',
    spent_this_month_usd: '5.000000',
    key_status: 'working',
    tiers: [
      { tier: 'fast', provider: 'openai', model: 'gpt-5.4-mini' },
      { tier: 'strong', provider: 'openai', model: 'gpt-6-astra' },
    ],
    ...overrides,
  }
}

let calls: { method: string; url: string; body?: string }[]
let reply: Record<string, unknown>
let put: () => Response

function serve() {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? 'GET'
      calls.push({ method, url, body: init?.body as string | undefined })
      if (method === 'PUT') return put()
      if (method === 'POST') return json({ status: 'queued' }, 202)
      return json(reply)
    }),
  )
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <SettingsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  calls = []
  reply = settings()
  put = () => json({ status: 'saved' })
  serve()
})
afterEach(() => vi.unstubAllGlobals())

describe('SettingsPage', () => {
  it('US3_AS4_shows_status_cap_spend_tiers', async () => {
    renderPage()

    expect(await screen.findByText('Found, working')).toBeInTheDocument()
    expect(screen.getByLabelText('Monthly budget cap (USD)')).toHaveValue('25')
    expect(screen.getByText(/\$5\.00 of \$25\.00/)).toBeInTheDocument()
    const bar = screen.getByRole('progressbar', { name: 'Spent this month' })
    expect(bar).toHaveAttribute('aria-valuenow', '20')
    const table = screen.getByRole('table', { name: 'Models by tier' })
    expect(within(table).getByRole('row', { name: /fast.*gpt-5\.4-mini/ })).toBeInTheDocument()
    expect(within(table).getByRole('row', { name: /strong.*gpt-6-astra/ })).toBeInTheDocument()
  })

  it('shows_a_missing_key_with_how_to_fix_it', async () => {
    reply = settings({ key_status: 'missing' })
    renderPage()
    expect(await screen.findByText('Missing')).toBeInTheDocument()
    expect(screen.getByText(/Add OPENAI_API_KEY to .env/)).toBeInTheDocument()
  })

  it('check_again_asks_the_server_to_recheck', async () => {
    const user = userEvent.setup()
    renderPage()
    await user.click(await screen.findByRole('button', { name: 'Check again' }))
    await waitFor(() =>
      expect(calls.some((c) => c.method === 'POST' && c.url.endsWith('/status/ai/check'))).toBe(true),
    )
  })

  it('saves_a_new_cap', async () => {
    const user = userEvent.setup()
    renderPage()
    const input = await screen.findByLabelText('Monthly budget cap (USD)')
    await user.clear(input)
    await user.type(input, '40.5')
    await user.click(screen.getByRole('button', { name: 'Save cap' }))

    await waitFor(() => expect(calls.some((c) => c.method === 'PUT')).toBe(true))
    expect(JSON.parse(calls.find((c) => c.method === 'PUT')?.body ?? '{}')).toEqual({
      budget_cap_usd: '40.5',
    })
    expect(await screen.findByText('Saved')).toBeInTheDocument()
  })

  it('rejects_a_cap_outside_0_to_10000_before_saving', async () => {
    const user = userEvent.setup()
    renderPage()
    const input = await screen.findByLabelText('Monthly budget cap (USD)')
    await user.clear(input)
    await user.type(input, '20000')
    await user.click(screen.getByRole('button', { name: 'Save cap' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('between 0 and 10000')
    expect(calls.some((c) => c.method === 'PUT')).toBe(false)
  })

  it('shows_a_server_error_next_to_the_cap', async () => {
    put = () =>
      json(
        {
          title: 'Some fields are not valid.',
          status: 422,
          errors: [{ field: 'budget_cap_usd', message: 'The budget cap must be between 0 and 10000 USD' }],
        },
        422,
        'application/problem+json',
      )
    const user = userEvent.setup()
    renderPage()
    await user.click(await screen.findByRole('button', { name: 'Save cap' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('between 0 and 10000')
  })

  it('US3_AS5_budget_reached_notice_links_here', async () => {
    reply = settings({ spent_this_month_usd: '25.000000' })
    renderPage()
    const notice = await screen.findByRole('status', { name: 'Budget' })
    expect(notice).toHaveTextContent('reached this month')
    expect(notice).toHaveTextContent('Raise the cap')
  })

  it('clarification_Q2_tiers_not_editable', async () => {
    renderPage()
    const table = await screen.findByRole('table', { name: 'Models by tier' })
    expect(within(table).queryByRole('textbox')).not.toBeInTheDocument()
    expect(within(table).queryByRole('combobox')).not.toBeInTheDocument()
    expect(screen.getAllByRole('textbox')).toHaveLength(1) // only the budget cap
  })

  it('never_shows_a_key_field', async () => {
    renderPage()
    await screen.findByText('Found, working')
    expect(screen.queryByLabelText(/api key/i)).not.toBeInTheDocument()
  })
})
