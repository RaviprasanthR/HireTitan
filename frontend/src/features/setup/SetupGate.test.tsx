import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { routes } from '@/app/routes'

const json = (body: unknown) =>
  new Response(JSON.stringify(body), {
    headers: { 'Content-Type': 'application/json' },
  })

type Step = 1 | 2 | 3 | 4 | 'done'

function onboarding(step: Step, name: string | null = 'Jane') {
  return {
    step,
    display_name: name,
    open_review_id: null,
    active_run_id: null,
  }
}

function aiStatus(status = 'working') {
  return {
    ai: { provider: 'openai', status, message: null, checked_at: null },
    checklist: {
      key_ok: status === 'working',
      resume_uploaded: false,
      profile_confirmed: false,
      preferences_saved: false,
    },
    budget: { cap_usd: '25.00', spent_usd: '0', period: '2026-11' },
  }
}

function renderAt(path: string, step: Step, status = 'working') {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) => {
      if (url.endsWith('/onboarding')) return json(onboarding(step, step === 1 ? null : 'Jane'))
      if (url.endsWith('/status')) return json(aiStatus(status))
      if (url.endsWith('/settings')) {
        return json({
          budget_cap_usd: '25.00',
          spent_this_month_usd: '0',
          key_status: status,
          tiers: [],
        })
      }
      if (url.endsWith('/profile')) return json({ current: null })
      return json([])
    }),
  )
  const router = createMemoryRouter(routes, { initialEntries: [path] })
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  )
}

describe('SetupGate', () => {
  afterEach(() => vi.unstubAllGlobals())

  it.each(['/', '/profile', '/preferences', '/review', '/nope'])(
    'US5_AS1_any_url_shows_setup_card_without_sidebar %s',
    async (path) => {
      renderAt(path, 1)
      expect(await screen.findByText('Step 1 of 4')).toBeInTheDocument()
      expect(screen.queryByRole('navigation', { name: 'Main' })).not.toBeInTheDocument()
      expect(screen.queryByTestId('app-root')).not.toBeInTheDocument()
    },
  )

  it.each([
    [1, 'Step 1 of 4'],
    [2, 'Step 2 of 4'],
    [3, 'Step 3 of 4'],
    [4, 'Step 4 of 4'],
  ] as const)('US5_AS3_resumes_at_saved_step %s', async (step, label) => {
    renderAt('/', step)
    expect(await screen.findByText(label)).toBeInTheDocument()
    expect(screen.getByRole('progressbar', { name: 'Setup progress' })).toHaveAttribute(
      'aria-valuenow',
      String(step),
    )
  })

  it('US5_AS7_done_shows_the_shell', async () => {
    renderAt('/', 'done')
    expect(await screen.findByRole('navigation', { name: 'Main' })).toBeInTheDocument()
    expect(screen.queryByText(/Step \d of 4/)).not.toBeInTheDocument()
  })

  it('FR041_settings_reachable_during_setup', async () => {
    renderAt('/settings', 2)
    expect(await screen.findByRole('heading', { level: 1, name: 'Settings' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Back to setup' })).toHaveAttribute('href', '/')
    expect(screen.queryByRole('navigation', { name: 'Main' })).not.toBeInTheDocument()
  })

  it('FR041_setup_cards_link_to_settings', async () => {
    renderAt('/', 2)
    expect(await screen.findByRole('link', { name: 'AI budget and key settings' })).toHaveAttribute(
      'href',
      '/settings',
    )
  })

  it('FR030_banner_on_setup_cards', async () => {
    renderAt('/', 2, 'missing')
    const banner = await screen.findByRole('alert', { name: 'AI status' })
    expect(banner).toHaveTextContent('AI key is missing')
  })

  it('shows_a_load_error_instead_of_the_app', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response('{}', { status: 500 })),
    )
    const router = createMemoryRouter(routes, { initialEntries: ['/'] })
    render(
      <QueryClientProvider
        client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
      >
        <RouterProvider router={router} />
      </QueryClientProvider>,
    )
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not load')
  })
})
