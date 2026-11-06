import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { routes } from './routes'

const json = (body: unknown) =>
  new Response(JSON.stringify(body), { headers: { 'Content-Type': 'application/json' } })

function status(aiStatus: string, message: string | null = null) {
  return {
    ai: { provider: 'openai', status: aiStatus, message, checked_at: null },
    checklist: {
      key_ok: aiStatus === 'working',
      resume_uploaded: false,
      profile_confirmed: false,
      preferences_saved: false,
      rules_approved: false,
      searched_once: false,
    },
    budget: { cap_usd: '25.00', spent_usd: '0', period: '2026-11' },
  }
}

function renderAt(path: string, aiStatus: string, message: string | null = null) {
  const fetchMock = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>(async (url) =>
    url.endsWith('/status')
      ? json(status(aiStatus, message))
      : url.endsWith('/onboarding')
        ? json({ step: 'done', display_name: 'Jane', open_review_id: null, active_run_id: null })
        : url.includes('/jobs')
          ? json({ items: [], next_cursor: null })
          : url.endsWith('/search/latest')
            ? json(null)
            : json([]),
  )
  vi.stubGlobal('fetch', fetchMock)
  const router = createMemoryRouter(routes, { initialEntries: [path] })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  )
  return fetchMock
}

describe('AiBanner', () => {
  afterEach(() => vi.unstubAllGlobals())

  it.each(['/', '/profile', '/settings', '/review'])(
    'US3_AS1_banner_on_every_page_when_missing %s',
    async (path) => {
      renderAt(path, 'missing')
      const banner = await screen.findByRole('alert', { name: 'AI status' })
      expect(banner).toHaveTextContent('AI key is missing')
      expect(banner).toHaveTextContent('Add OPENAI_API_KEY to .env, then restart')
    },
  )

  it('US3_AS2_rejected_message', async () => {
    renderAt('/', 'rejected')
    const banner = await screen.findByRole('alert', { name: 'AI status' })
    expect(banner).toHaveTextContent('rejected')
    expect(banner).toHaveTextContent('Replace OPENAI_API_KEY in .env, then restart')
  })

  it('unreachable_is_a_softer_warning', async () => {
    renderAt('/', 'unreachable')
    const banner = await screen.findByRole('status', { name: 'AI status' })
    expect(banner).toHaveTextContent('could not be reached')
    expect(screen.queryByRole('alert', { name: 'AI status' })).not.toBeInTheDocument()
  })

  it('R7_shows_out_of_credit_message', async () => {
    renderAt('/', 'out_of_credit', 'You exceeded your current quota, please check your billing.')
    const banner = await screen.findByRole('alert', { name: 'AI status' })
    expect(banner).toHaveTextContent('Your AI account is out of credit')
    expect(banner).toHaveTextContent('You exceeded your current quota, please check your billing.')
    expect(banner).toHaveTextContent('paused, not lost')
  })

  it('R7_check_again_asks_the_server_to_recheck', async () => {
    const user = userEvent.setup()
    const fetchMock = renderAt('/', 'out_of_credit', 'No credit.')
    await screen.findByRole('heading', { level: 1, name: 'Jobs' })
    await user.click(await screen.findByRole('button', { name: 'Check again' }))
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(
          ([url, init]) =>
            String(url).endsWith('/status/ai/check') &&
            (init as RequestInit | undefined)?.method === 'POST',
        ),
      ).toBe(true),
    )
  })

  it.each(['working', 'unknown'])('no_banner_when_%s', async (aiStatus) => {
    renderAt('/', aiStatus)
    await screen.findByRole('heading', { level: 1, name: 'Jobs' })
    expect(screen.queryByRole('alert', { name: 'AI status' })).not.toBeInTheDocument()
    expect(screen.queryByRole('status', { name: 'AI status' })).not.toBeInTheDocument()
  })
})
