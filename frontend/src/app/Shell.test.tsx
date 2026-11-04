import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
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
      url.endsWith('/profile') ? reply({ current: profile ? { id: 'v1' } : null }) : reply([]),
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

  it('FR027_sidebar_has_five_sections', async () => {
    renderAt('/')
    const nav = screen.getByRole('navigation', { name: 'Main' })
    await screen.findByRole('link', { name: 'Preferences' })
    const links = within(nav).getAllByRole('link')
    expect(links.map((link) => link.textContent)).toEqual([
      'Home',
      'Profile',
      'Preferences',
      'Review',
      'Settings',
    ])
  })

  it('preferences_hidden_until_a_profile_is_confirmed', async () => {
    renderAt('/', false)
    const nav = screen.getByRole('navigation', { name: 'Main' })
    await screen.findByRole('link', { name: 'Profile' })
    await waitFor(() => expect(within(nav).queryByRole('link', { name: 'Preferences' })).toBeNull())
    expect(within(nav).getAllByRole('link')).toHaveLength(4)
  })

  it('preferences_route_sends_you_to_profile_without_a_profile', async () => {
    renderAt('/preferences', false)
    expect(await screen.findByRole('heading', { level: 1, name: 'Profile' })).toBeInTheDocument()
  })

  it('marks_the_current_section', () => {
    renderAt('/profile')
    expect(screen.getByRole('link', { name: 'Profile' })).toHaveAttribute('aria-current', 'page')
    expect(screen.getByRole('link', { name: 'Home' })).not.toHaveAttribute('aria-current')
  })

  it.each([
    ['/', 'Home'],
    ['/profile', 'Profile'],
    ['/preferences', 'Preferences'],
    ['/review', 'Review'],
    ['/settings', 'Settings'],
  ])('route_%s_renders_%s', async (path, heading) => {
    renderAt(path)
    expect(await screen.findByRole('heading', { level: 1, name: heading })).toBeInTheDocument()
  })

  it('review_route_shows_the_editor_loading', () => {
    renderAt('/profile/review/abc')
    expect(screen.getByText('Loading your review…')).toBeInTheDocument()
  })

  it('versions_route_lists_versions', async () => {
    renderAt('/profile/versions')
    expect(
      await screen.findByRole('heading', { level: 1, name: 'Profile versions' }),
    ).toBeInTheDocument()
  })

  it('version_route_shows_the_version_loading', () => {
    renderAt('/profile/versions/v1')
    expect(screen.getByText('Loading this version…')).toBeInTheDocument()
  })

  it('has_a_banner_slot_above_the_page', () => {
    renderAt('/')
    expect(screen.getByTestId('banner-slot')).toBeInTheDocument()
  })

  it('unknown_path_shows_not_found_inside_the_shell', () => {
    renderAt('/nope')
    expect(screen.getByRole('heading', { level: 1, name: 'Page not found' })).toBeInTheDocument()
    expect(screen.getByRole('navigation', { name: 'Main' })).toBeInTheDocument()
  })
})
