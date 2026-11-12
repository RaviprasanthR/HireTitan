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
      url.endsWith('/status')
        ? reply({
            ai: { provider: 'openai', status: 'working', message: null, checked_at: null },
            checklist: { key_ok: true },
          })
        : url.endsWith('/onboarding')
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

  it('US4 the menu has no Preferences or Search rules entry (they are Profile tabs)', async () => {
    renderAt('/')
    const nav = await screen.findByRole('navigation', { name: 'Main' })
    const links = within(nav).getAllByRole('link')
    expect(links.map((link) => link.textContent)).toEqual([
      'Home',
      'Profile',
      'Companies',
      'Review',
      'Settings',
    ])
  })

  it('US1 AS4 an old applied link opens the pipeline tab', async () => {
    renderAt('/applied')

    const tabs = await screen.findByRole('navigation', { name: 'Home tabs' })

    expect(within(tabs).getByRole('link', { name: 'In pipeline' })).toHaveAttribute(
      'aria-current',
      'page',
    )
  })

  it('the window does not scroll: the menu stays put and the page area scrolls on its own', async () => {
    renderAt('/')
    await screen.findByRole('navigation', { name: 'Main' })

    expect(screen.getByTestId('app-root')).toHaveClass('h-screen', 'overflow-hidden')
    expect(screen.getByRole('main')).toHaveClass('overflow-y-auto')
  })

  it('FR022 every menu item has an outline icon', async () => {
    renderAt('/')
    const nav = await screen.findByRole('navigation', { name: 'Main' })

    for (const link of within(nav).getAllByRole('link')) {
      const icon = link.querySelector('svg')
      expect(icon, link.textContent ?? '').not.toBeNull()
      expect(icon).toHaveAttribute('aria-hidden', 'true')
    }
  })

  it('FR022 the app name is plain text at the top of the sidebar, with no logo', async () => {
    renderAt('/')
    const nav = await screen.findByRole('navigation', { name: 'Main' })
    const sidebar = nav.closest('aside') as HTMLElement

    expect(within(sidebar).getAllByText('HireTitan')).toHaveLength(1)
    expect(sidebar.firstElementChild).toHaveTextContent('HireTitan')
    // the only graphics in the sidebar are the eight menu icons
    expect(sidebar.querySelectorAll('svg')).toHaveLength(within(nav).getAllByRole('link').length)
    expect(sidebar.querySelector('img')).toBeNull()
  })

  it('FR022 the sidebar has a thin divider on its right edge', async () => {
    renderAt('/')
    const nav = await screen.findByRole('navigation', { name: 'Main' })

    expect(nav.closest('aside')).toHaveClass('border-r')
  })

  it('marks_the_current_section', async () => {
    renderAt('/profile')
    const nav = await screen.findByRole('navigation', { name: 'Main' })
    expect(within(nav).getByRole('link', { name: 'Profile' })).toHaveAttribute(
      'aria-current',
      'page',
    )
    expect(within(nav).getByRole('link', { name: 'Home' })).not.toHaveAttribute('aria-current')
  })

  it.each([
    ['/', 'Jobs'],
    ['/profile', 'Profile'],
    ['/profile/preferences', 'Preferences'],
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
