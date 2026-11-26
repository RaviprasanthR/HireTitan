import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, within } from '@testing-library/react'
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
      'Companies',
      'Profile',
      'Settings',
    ])
  })

  it('Home opens on the In pipeline tab, and Explore lives at /explore with Home still lit', async () => {
    renderAt('/')
    const tabs = await screen.findByRole('navigation', { name: 'Home tabs' })
    expect(within(tabs).getByRole('link', { name: 'In pipeline' })).toHaveAttribute(
      'aria-current',
      'page',
    )
    expect(within(tabs).getByRole('link', { name: 'Explore' })).toHaveAttribute('href', '/explore')
  })

  it('the Explore tab keeps Home active in the menu', async () => {
    renderAt('/explore')
    const tabs = await screen.findByRole('navigation', { name: 'Home tabs' })
    expect(within(tabs).getByRole('link', { name: 'Explore' })).toHaveAttribute(
      'aria-current',
      'page',
    )
    const main = screen.getByRole('navigation', { name: 'Main' })
    expect(within(main).getByRole('link', { name: 'Home' })).toHaveAttribute('aria-current', 'page')
  })

  it('US1 AS4 an old applied link opens the pipeline tab', async () => {
    renderAt('/applied')

    const tabs = await screen.findByRole('navigation', { name: 'Home tabs' })

    expect(within(tabs).getByRole('link', { name: 'In pipeline' })).toHaveAttribute(
      'aria-current',
      'page',
    )
  })

  it('the window does not scroll: the top bar stays put and the page area scrolls on its own', async () => {
    renderAt('/')
    await screen.findByRole('navigation', { name: 'Main' })

    expect(screen.getByTestId('app-root')).toHaveClass('h-screen', 'overflow-hidden', 'flex-col')
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

  it('FR022 the logo and the app name are at the left of the top bar, before the menu', async () => {
    renderAt('/')
    const nav = await screen.findByRole('navigation', { name: 'Main' })
    const bar = nav.closest('header') as HTMLElement

    expect(within(bar).getAllByText('HireTitan')).toHaveLength(1)
    expect(bar.firstElementChild).toHaveTextContent('HireTitan')
    expect(bar.firstElementChild?.querySelector('svg[data-logo]')).not.toBeNull()
    expect(bar.querySelector('img')).toBeNull()
    // the menu runs in a row beside the name, not down the left edge
    expect(nav).toHaveClass('flex', 'items-center')
    expect(nav.closest('aside')).toBeNull()
  })

  it('FR022 the top bar has a thin divider on its bottom edge', async () => {
    renderAt('/')
    const nav = await screen.findByRole('navigation', { name: 'Main' })

    expect(nav.closest('header')).toHaveClass('border-b')
  })

  it('002m the chat button is at the bottom right of every page and opens a popup', async () => {
    renderAt('/companies')
    const launcher = await screen.findByRole('button', { name: 'Mikasa' })
    expect(launcher).toHaveClass('fixed', 'bottom-5', 'right-5')
    expect(launcher).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByRole('complementary', { name: 'Mikasa' })).not.toBeInTheDocument()

    fireEvent.click(launcher)

    const popup = screen.getByRole('complementary', { name: 'Mikasa' })
    expect(popup).toHaveClass('fixed', 'bottom-24', 'right-5', 'mikasa-pop')
    expect(launcher).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByRole('main')).toBeInTheDocument() // the page stays under it
    fireEvent.click(launcher)
    expect(screen.queryByRole('complementary', { name: 'Mikasa' })).not.toBeInTheDocument()
  })

  it('002m Ctrl+/ toggles the popup and Escape closes it', async () => {
    renderAt('/')
    await screen.findByRole('button', { name: 'Mikasa' })

    fireEvent.keyDown(window, { key: '/', ctrlKey: true })
    expect(screen.getByRole('complementary', { name: 'Mikasa' })).toBeInTheDocument()
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(screen.queryByRole('complementary', { name: 'Mikasa' })).not.toBeInTheDocument()
    fireEvent.keyDown(window, { key: '/', ctrlKey: true })
    expect(screen.getByRole('complementary', { name: 'Mikasa' })).toBeInTheDocument()
  })

  it('the logo sits alone at the left of the top bar and the menu at the right', async () => {
    renderAt('/')
    const nav = await screen.findByRole('navigation', { name: 'Main' })
    const bar = nav.closest('header') as HTMLElement

    expect(bar).toHaveClass('justify-between')
    expect(bar.firstElementChild).not.toContainElement(nav)
    expect(bar.lastElementChild).toBe(nav)
  })

  it('the current section is marked by a glowing bar, not a filled button', async () => {
    renderAt('/companies')
    const nav = await screen.findByRole('navigation', { name: 'Main' })
    const current = within(nav).getByRole('link', { name: 'Companies' })

    expect(current).not.toHaveClass('bg-primary')
    expect(current.querySelector('span[aria-hidden]')).toHaveClass('scale-x-100')
    const other = within(nav).getByRole('link', { name: 'Profile' })
    expect(other.querySelector('span[aria-hidden]')).toHaveClass('scale-x-0')
  })

  it('pages sit in a wide centred column with a little room on both sides', async () => {
    renderAt('/')
    const column = await screen.findByTestId('page-column')
    expect(column).toHaveClass('mx-auto', 'max-w-[1440px]', 'px-4', 'md:px-6')
  })

  it('the chat floats over the page: opening it does not move the page', async () => {
    renderAt('/')
    const column = await screen.findByTestId('page-column')
    const before = column.className

    fireEvent.click(screen.getByRole('button', { name: 'Mikasa' }))

    expect(column.className).toBe(before)
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
