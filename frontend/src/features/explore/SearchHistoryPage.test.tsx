import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { stubApi } from '@/test/api'
import { SearchHistoryPage } from './SearchHistoryPage'

function run(id: string, over: Record<string, unknown> = {}) {
  return {
    id,
    run_id: `r-${id}`,
    mode: 'rules_and_ai',
    outcome: 'finished',
    stop_message: null,
    stop_requested: false,
    batches_done: 3,
    companies_total: 20,
    companies_read: 20,
    jobs_found: 120,
    skipped_by_rules: 80,
    judged_by_ai: 30,
    kept: 12,
    added: 14,
    merged: 2,
    not_checked_by_ai: 2,
    ai_cost_usd: '0.0412',
    ai_note: null,
    started_at: '2026-11-06T09:00:00Z',
    finished_at: '2026-11-06T09:10:00Z',
    ...over,
  }
}

afterEach(() => vi.unstubAllGlobals())

describe('SearchHistoryPage', () => {
  it('FR042_lists_runs_newest_first_with_cost', async () => {
    stubApi((call) =>
      call.path.startsWith('/search/runs')
        ? {
            items: [
              run('new', { outcome: 'out_of_credit', ai_cost_usd: '0.5000', added: 3 }),
              run('old'),
            ],
            next_cursor: null,
          }
        : undefined,
    )
    render(
      <QueryClientProvider
        client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
      >
        <MemoryRouter>
          <SearchHistoryPage />
        </MemoryRouter>
      </QueryClientProvider>,
    )

    const list = await screen.findByRole('list', { name: 'Searches' })
    const items = within(list).getAllByRole('listitem')
    expect(items).toHaveLength(2)
    expect(items[0]).toHaveTextContent('Out of credit')
    expect(items[0]).toHaveTextContent('$0.5000')
    expect(items[0]).toHaveTextContent('3 jobs added')
    expect(items[1]).toHaveTextContent('Finished')
    expect(items[1]).toHaveTextContent('$0.0412')
    expect(within(items[0] as HTMLElement).getByRole('link', { name: /summary/i })).toHaveAttribute(
      'href',
      '/search/runs/new',
    )
  })

  it('says_so_when_there_are_no_searches', async () => {
    stubApi(() => ({ items: [], next_cursor: null }))
    render(
      <QueryClientProvider
        client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
      >
        <MemoryRouter>
          <SearchHistoryPage />
        </MemoryRouter>
      </QueryClientProvider>,
    )
    expect(await screen.findByText(/No searches yet/)).toBeInTheDocument()
  })
})
