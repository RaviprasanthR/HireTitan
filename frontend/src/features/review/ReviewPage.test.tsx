import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ReviewPage } from './ReviewPage'

const json = (body: unknown) =>
  new Response(JSON.stringify(body), { headers: { 'Content-Type': 'application/json' } })

function renderPage(items: unknown[]) {
  vi.stubGlobal('fetch', vi.fn(async () => json(items)))
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <ReviewPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('ReviewPage', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('US3_AS6_items_link_to_targets', async () => {
    renderPage([
      {
        id: 'r1',
        kind: 'paused',
        title: 'Paused: monthly AI budget reached',
        target: '/settings',
        updated_at: '2026-11-04T10:00:00Z',
      },
      {
        id: 'r2',
        kind: 'profile_review',
        title: 'Review the profile extracted from your resume',
        target: '/profile/review/abc',
        updated_at: '2026-11-04T09:00:00Z',
      },
      {
        id: 'r3',
        kind: 'injection_decision',
        title: 'Decide what to do about suspicious text in your resume',
        target: '/profile',
        updated_at: '2026-11-04T08:00:00Z',
      },
    ])

    const links = await screen.findAllByRole('link')
    expect(links.map((l) => l.getAttribute('href'))).toEqual([
      '/settings',
      '/profile/review/abc',
      '/profile',
    ])
    expect(links[0]).toHaveTextContent('Paused: monthly AI budget reached')
  })

  it('empty_list_says_nothing_is_waiting', async () => {
    renderPage([])
    expect(await screen.findByText('Nothing is waiting for you.')).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 1, name: 'Review' })).toBeInTheDocument()
  })

  it('shows_a_load_error', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('{}', { status: 500 })))
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter>
          <ReviewPage />
        </MemoryRouter>
      </QueryClientProvider>,
    )
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not load')
  })
})
