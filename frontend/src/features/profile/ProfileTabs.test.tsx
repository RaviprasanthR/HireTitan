import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { routes } from '@/app/routes'

function renderAt(path: string) {
  const reply = (body: unknown) =>
    new Response(JSON.stringify(body), { headers: { 'Content-Type': 'application/json' } })
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) =>
      url.endsWith('/status')
        ? reply({
            ai: { provider: 'openai', status: 'working', message: null, checked_at: null },
            checklist: { key_ok: true },
          })
        : url.endsWith('/onboarding')
          ? reply({ step: 'done', display_name: 'Jane', open_review_id: null, active_run_id: null })
          : url.endsWith('/profile')
            ? reply({ current: { id: 'v1' } })
            : url.endsWith('/preferences')
              ? reply({
                  content: {
                    target_roles: [],
                    seniority_levels: [],
                    years_experience: null,
                    key_skills: [],
                    preferred_locations: [],
                    default_country: 'IN',
                    work_modes: ['remote'],
                    willing_to_relocate: false,
                    blocked_locations: [],
                    job_types: ['full_time'],
                    pay: { currency: 'INR', min_annual: null, target_annual: null, basis: 'fixed' },
                    notice_period_days: 30,
                    earliest_start_date: null,
                    preferred_companies: [],
                    avoided_companies: [],
                  },
                  saved_at: null,
                  suggestions: { target_roles: [], key_skills: [] },
                })
              : reply([]),
    ),
  )
  const router = createMemoryRouter(routes, { initialEntries: [path] })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  )
  return router
}

describe('Profile tabs', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('US4 AS1 the profile page has the three tabs, Profile first', async () => {
    renderAt('/profile')

    const tabs = await screen.findByRole('navigation', { name: 'Profile tabs' })

    expect(
      within(tabs)
        .getAllByRole('link')
        .map((l) => l.textContent),
    ).toEqual(['Profile', 'Preferences', 'Search rules'])
    expect(within(tabs).getByRole('link', { name: 'Profile' })).toHaveAttribute(
      'aria-current',
      'page',
    )
  })

  it('US4 AS1 the preferences tab shows the preferences form', async () => {
    renderAt('/profile/preferences')

    const tabs = await screen.findByRole('navigation', { name: 'Profile tabs' })

    expect(within(tabs).getByRole('link', { name: 'Preferences' })).toHaveAttribute(
      'aria-current',
      'page',
    )
    await screen.findByLabelText(/target roles/i)
    expect(screen.getByRole('heading', { level: 1, name: 'Preferences' })).toBeInTheDocument()
  })

  it('US4 AS2 the search rules tab shows the search rules', async () => {
    renderAt('/profile/search-rules')

    const tabs = await screen.findByRole('navigation', { name: 'Profile tabs' })

    expect(within(tabs).getByRole('link', { name: 'Search rules' })).toHaveAttribute(
      'aria-current',
      'page',
    )
    expect(
      await screen.findByRole('heading', { level: 1, name: 'Search rules' }),
    ).toBeInTheDocument()
  })

  it.each([
    ['/preferences', '/profile/preferences'],
    ['/search/rules', '/profile/search-rules'],
  ])('US4 AS3 the old address %s opens the tab at %s', async (old, now) => {
    const router = renderAt(old)

    await screen.findByRole('navigation', { name: 'Profile tabs' })

    expect(router.state.location.pathname).toBe(now)
  })

  it('US4 AS3 an old address does not stay in the back history', async () => {
    const router = renderAt('/preferences')
    await screen.findByRole('navigation', { name: 'Profile tabs' })

    await router.navigate(-1).catch(() => undefined)

    expect(router.state.location.pathname).not.toBe('/preferences')
  })

  it('the other profile pages (edit, versions) have no tabs', async () => {
    renderAt('/profile/versions')

    await screen.findByRole('heading', { level: 1, name: 'Profile versions' })

    expect(screen.queryByRole('navigation', { name: 'Profile tabs' })).not.toBeInTheDocument()
  })
})
