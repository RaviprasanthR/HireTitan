import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
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
  }
}

function renderAt(path: string, step: Step, status = 'working') {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) => {
      if (url.endsWith('/onboarding')) return json(onboarding(step, step === 1 ? null : 'Jane'))
      if (url.endsWith('/status')) return json(aiStatus(status))
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

  it.each(['/', '/profile', '/profile/preferences', '/review', '/nope'])(
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

  it.each([
    [1, '25%'],
    [2, '50%'],
    [3, '75%'],
    [4, '100%'],
  ] as const)('the_step_bar_fill_is_visible_at_step %s', async (step, width) => {
    renderAt('/', step)
    const bar = await screen.findByRole('progressbar', { name: 'Setup progress' })
    // the themed track and fill, not the navy `bg-primary` that matches the track's colour
    expect(bar).toHaveClass('ht-progress')
    // orange, the brand accent: green is kept for "done", and the resume bar
    expect(bar).toHaveAttribute('data-tone', 'accent')
    const fill = within(bar).getByTestId('progress-fill')
    expect(fill).toHaveClass('ht-progress-fill')
    expect(fill).toHaveStyle({ width })
  })

  // the card the step sits in: wide for the steps that hold a lot (US4, FR-021)
  const cardOf = (label: string) => screen.getByText(label).closest('.bg-surface') as HTMLElement

  it.each([
    [1, 'Step 1 of 4'],
    [2, 'Step 2 of 4'],
  ] as const)('FR021_the_name_and_resume_steps_stay_narrow %s', async (step, label) => {
    renderAt('/', step)
    await screen.findByText(label)
    expect(cardOf(label)).toHaveClass('max-w-2xl')
    expect(cardOf(label)).not.toHaveClass('max-w-6xl')
  })

  it.each([
    [3, 'Step 3 of 4'],
    [4, 'Step 4 of 4'],
  ] as const)('FR021_the_review_and_preferences_steps_use_a_wide_card %s', async (step, label) => {
    renderAt('/', step)
    await screen.findByText(label)
    expect(cardOf(label)).toHaveClass('max-w-6xl')
    expect(cardOf(label)).not.toHaveClass('max-w-2xl')
  })

  it('FR021_going_back_to_the_name_makes_the_card_narrow_again', async () => {
    const user = userEvent.setup()
    renderAt('/', 2)
    await user.click(await screen.findByRole('button', { name: /back/i }))
    expect(cardOf('Step 1 of 4')).toHaveClass('max-w-2xl')
  })

  it('FR021_settings_during_setup_keeps_the_narrow_card', async () => {
    renderAt('/settings', 4)
    await screen.findByRole('link', { name: 'Close settings' })
    expect(
      screen.getByRole('link', { name: 'Close settings' }).closest('.bg-surface'),
    ).toHaveClass('max-w-2xl')
  })

  it('going_back_to_the_name_lowers_the_step_bar', async () => {
    const user = userEvent.setup()
    renderAt('/', 2)
    expect(await screen.findByText('Step 2 of 4')).toBeInTheDocument()

    await user.click(await screen.findByRole('button', { name: 'Back' }))

    expect(await screen.findByText('Step 1 of 4')).toBeInTheDocument()
    expect(screen.getByRole('progressbar', { name: 'Setup progress' })).toHaveAttribute(
      'aria-valuenow',
      '1',
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
    const close = screen.getByRole('link', { name: 'Close settings' })
    expect(close).toHaveAttribute('href', '/')
    expect(close.querySelector('svg')).not.toBeNull() // the cross icon
    expect(close).toHaveClass('text-danger') // red, top right of the card
    expect(screen.queryByText('Back to setup')).not.toBeInTheDocument()
    expect(screen.queryByRole('navigation', { name: 'Main' })).not.toBeInTheDocument()
  })

  it('FR041_setup_cards_link_to_settings', async () => {
    renderAt('/', 2)
    expect(await screen.findByRole('link', { name: 'AI key settings' })).toHaveAttribute(
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
