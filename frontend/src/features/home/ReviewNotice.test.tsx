import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { routes } from '@/app/routes'
import { ReviewNotice } from './ReviewNotice'

function items(n: number) {
  return Array.from({ length: n }, (_, i) => ({
    id: `r${i}`,
    title: `Item ${i}`,
    target: '/profile',
    updated_at: '2026-11-01T10:00:00Z',
  }))
}

function stub(reviewItems: unknown[]) {
  const reply = (body: unknown) =>
    new Response(JSON.stringify(body), { headers: { 'Content-Type': 'application/json' } })
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) =>
      url.endsWith('/review-items')
        ? reply(reviewItems)
        : url.endsWith('/status')
          ? reply({
              ai: { provider: 'openai', status: 'working', message: null, checked_at: null },
              checklist: { key_ok: true },
            })
          : url.endsWith('/onboarding')
            ? reply({
                step: 'done',
                display_name: 'Jane',
                open_review_id: null,
                active_run_id: null,
              })
            : url.endsWith('/profile')
              ? reply({ current: { id: 'v1' } })
              : url.includes('/jobs')
                ? reply({ items: [], next_cursor: null })
                : url.endsWith('/search/latest')
                  ? reply(null)
                  : reply([]),
    ),
  )
}

function renderAt(path: string) {
  const router = createMemoryRouter(routes, { initialEntries: [path] })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  )
}

describe('ReviewNotice', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('SC001 menu has four entries: Home, Companies, Profile, Settings', async () => {
    stub([])
    renderAt('/')
    const nav = await screen.findByRole('navigation', { name: 'Main' })

    expect(Array.from(nav.querySelectorAll('a')).map((a) => a.textContent)).toEqual([
      'Home',
      'Companies',
      'Profile',
      'Settings',
    ])
  })

  it.each(['/', '/pipeline'])(
    'US5 AS2 %s shows the count and links to the review page',
    async (path) => {
      stub(items(1))
      renderAt(path)

      const link = await screen.findByRole('link', { name: '1 item needs your review' })

      expect(link).toHaveAttribute('href', '/review')
    },
  )

  it('US5 AS2 several items are counted', async () => {
    stub(items(3))
    renderAt('/')

    expect(await screen.findByRole('link', { name: '3 items need your review' })).toBeVisible()
  })

  it('US5 AS3 no notice when nothing waits', async () => {
    stub([])
    renderAt('/')
    await screen.findByRole('navigation', { name: 'Home tabs' })

    expect(screen.queryByText(/your review/)).not.toBeInTheDocument()
  })

  it('US5 AS4 the review page still opens', async () => {
    stub(items(1))
    renderAt('/review')

    expect(await screen.findByRole('heading', { level: 1, name: 'Review' })).toBeInTheDocument()
    expect(await screen.findByRole('link', { name: 'Item 0' })).toBeInTheDocument()
  })

  it('renders nothing while the list is loading or broken', () => {
    stub([])
    const client = new QueryClient()
    const { container } = render(
      <QueryClientProvider client={client}>
        <RouterProvider router={createMemoryRouter([{ path: '/', element: <ReviewNotice /> }])} />
      </QueryClientProvider>,
    )
    expect(container).toBeEmptyDOMElement()
  })
})
