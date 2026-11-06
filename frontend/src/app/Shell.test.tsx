import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { routes } from './routes'

function renderAt(path: string, profile = true) {
  // Pages that load data get an empty API; the shell itself is what these tests are about.
  const reply = (body: unknown) =>
    new Response(JSON.stringify(body), { headers: { 'Content-Type': 'application/json' } })
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) =>
      url.endsWith('/onboarding')
        ? reply({ step: 'done', display_name: 'Jane', open_review_id: null, active_run_id: null })
        : url.endsWith('/profile')
          ? reply({ current: profile ? { id: 'v1' } : null })
          : url.includes('/jobs')
            ? reply({ items: [], next_cursor: null })
            : url.endsWith('/search/latest')
              ? reply(null)
              : reply([]),
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

describe('Shell', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('FR027_sidebar_has_seven_sections', async () => {
    renderAt('/')
    const nav = await screen.findByRole('navigation', { name: 'Main' })
    const links = within(nav).getAllByRole('link')
    expect(links.map((link) => link.textContent)).toEqual([
      'Home',
      'Applied',
      'Profile',
      'Preferences',
      'Search rules',
      'Review',
      'Settings',
    ])
  })

  it('marks_the_current_section', async () => {
    renderAt('/profile')
    expect(await screen.findByRole('link', { name: 'Profile' })).toHaveAttribute(
      'aria-current',
      'page',
    )
    expect(screen.getByRole('link', { name: 'Home' })).not.toHaveAttribute('aria-current')
  })

  it.each([
    ['/', 'Jobs'],
    ['/profile', 'Profile'],
    ['/preferences', 'Preferences'],
    ['/review', 'Review'],
    ['/settings', 'Settings'],
  ])('route_%s_renders_%s', async (path, heading) => {
    renderAt(path)
    expect(await screen.findByRole('heading', { level: 1, name: heading })).toBeInTheDocument()
  })

  it('review_route_shows_the_editor_loading', async () => {
    renderAt('/profile/review/abc')
    expect(await screen.findByText('Loading your review…')).toBeInTheDocument()
  })

  it('versions_route_lists_versions', async () => {
    renderAt('/profile/versions')
    expect(
      await screen.findByRole('heading', { level: 1, name: 'Profile versions' }),
    ).toBeInTheDocument()
  })

  it('version_route_shows_the_version_loading', async () => {
    renderAt('/profile/versions/v1')
    expect(await screen.findByText('Loading this version…')).toBeInTheDocument()
  })

  it('has_a_banner_slot_above_the_page', async () => {
    renderAt('/')
    expect(await screen.findByTestId('banner-slot')).toBeInTheDocument()
  })

  it('unknown_path_shows_not_found_inside_the_shell', async () => {
    renderAt('/nope')
    expect(
      await screen.findByRole('heading', { level: 1, name: 'Page not found' }),
    ).toBeInTheDocument()
    expect(screen.getByRole('navigation', { name: 'Main' })).toBeInTheDocument()
  })
})
