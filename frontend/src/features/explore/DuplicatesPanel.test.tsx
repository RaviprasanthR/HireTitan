import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { stubApi } from '@/test/api'
import { DuplicatesPanel } from './DuplicatesPanel'

function job(id: string, title: string, url: string) {
  return {
    id,
    title,
    company_name: 'Acme',
    location_text: 'Pune, India',
    work_mode: null,
    posted_at: null,
    first_seen_at: '2026-11-05T00:00:00Z',
    state: 'explore',
    restored: false,
    sources: [{ kind: 'company_board', url }],
    decision: null,
    listed: true,
    applied_on: null,
  }
}

const PAIR = {
  id: 'p1',
  similarity: 0.92,
  status: 'open',
  decided_at: null,
  job_a: job('a', 'Backend Engineer', 'https://a.example.com/1'),
  job_b: job('b', 'Backend Engineer (Python)', 'https://b.example.com/2'),
}

function renderPanel(items: unknown[]) {
  const calls = stubApi((call) => {
    if (call.path === '/jobs/duplicates') return { items, next_cursor: null }
    if (call.path.startsWith('/jobs/duplicates/')) return { ...PAIR, status: 'merged' }
    return undefined
  })
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  render(
    <QueryClientProvider client={client}>
      <DuplicatesPanel />
    </QueryClientProvider>,
  )
  return calls
}

afterEach(() => vi.unstubAllGlobals())

describe('DuplicatesPanel', () => {
  it('FR021_merge_and_dismiss', async () => {
    const user = userEvent.setup()
    const calls = renderPanel([PAIR])

    const region = await screen.findByRole('region', {
      name: 'Possible duplicates',
    })
    expect(within(region).getByText('Backend Engineer')).toBeInTheDocument()
    expect(within(region).getByText('Backend Engineer (Python)')).toBeInTheDocument()
    expect(within(region).getByText('https://a.example.com/1')).toBeInTheDocument()
    expect(within(region).getByText('https://b.example.com/2')).toBeInTheDocument()

    await user.click(within(region).getByRole('button', { name: 'Merge' }))
    await waitFor(() =>
      expect(calls.some((c) => c.method === 'POST' && c.path === '/jobs/duplicates/p1/merge')).toBe(
        true,
      ),
    )

    await user.click(within(region).getByRole('button', { name: 'Not the same' }))
    await waitFor(() =>
      expect(
        calls.some((c) => c.method === 'POST' && c.path === '/jobs/duplicates/p1/dismiss'),
      ).toBe(true),
    )
  })

  it('shows_nothing_when_there_are_no_pairs', async () => {
    const calls = renderPanel([])
    await waitFor(() => expect(calls.length).toBeGreaterThan(0))
    expect(screen.queryByRole('region', { name: 'Possible duplicates' })).not.toBeInTheDocument()
  })
})
