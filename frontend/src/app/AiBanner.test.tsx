import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
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
    },
    budget: { cap_usd: '25.00', spent_usd: '0', period: '2026-11' },
  }
}

function renderAt(path: string, aiStatus: string) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) =>
      url.endsWith('/status') ? json(status(aiStatus)) : url.endsWith('/profile') ? json({ current: null }) : json([]),
    ),
  )
  const router = createMemoryRouter(routes, { initialEntries: [path] })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  )
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

  it.each(['working', 'unknown'])('no_banner_when_%s', async (aiStatus) => {
    renderAt('/', aiStatus)
    await screen.findByRole('heading', { level: 1, name: 'Home' })
    expect(screen.queryByRole('alert', { name: 'AI status' })).not.toBeInTheDocument()
    expect(screen.queryByRole('status', { name: 'AI status' })).not.toBeInTheDocument()
  })
})
