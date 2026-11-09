import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { problem, stubApi, type Call } from '@/test/api'
import { CompaniesPage } from './CompaniesPage'

function company(id: string, name: string, extra: Record<string, unknown> = {}) {
  return {
    id,
    origin: 'built_in',
    name,
    city: 'Pune',
    website: null,
    careers_url: `https://${name.toLowerCase()}.example.com/careers`,
    ats_vendor: 'lever',
    board_id: name.toLowerCase(),
    resolution: 'verified',
    board_status: 'board',
    hidden: false,
    user_modified: false,
    last_checked_at: null,
    last_check_result: null,
    last_check_error: null,
    ...extra,
  }
}

const ACME = company('a', 'Acme')
const KEKA = company('k', 'Keka', {
  ats_vendor: null,
  board_id: null,
  resolution: 'check_manually',
  board_status: 'check_manually',
  last_checked_at: '2026-11-05T09:00:00Z',
  last_check_result: 'unreadable',
})

function renderPage(handler: (call: Call) => unknown) {
  const calls = stubApi(handler)
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <CompaniesPage />
    </QueryClientProvider>,
  )
  return calls
}

afterEach(() => vi.unstubAllGlobals())

describe('CompaniesPage', () => {
  it('US3_AS1_lists_companies_with_board_status', async () => {
    renderPage((call) =>
      call.path.startsWith('/companies') ? { items: [ACME, KEKA], next_cursor: null } : undefined,
    )

    const list = await screen.findByRole('list', { name: 'Companies' })
    const [acme, keka] = within(list).getAllByRole('listitem')
    expect(acme).toHaveTextContent('Acme')
    expect(acme).toHaveTextContent('Job board')
    expect(acme).toHaveTextContent('Pune')
    expect(keka).toHaveTextContent('Check manually')
  })

  it('US3_AS4_hide_company', async () => {
    const user = userEvent.setup()
    const calls = renderPage((call) => {
      if (call.method === 'PATCH') return { ...ACME, hidden: true }
      return call.path.startsWith('/companies') ? { items: [ACME], next_cursor: null } : undefined
    })

    await user.click(await screen.findByRole('button', { name: 'Hide Acme' }))

    await waitFor(() =>
      expect(calls).toContainEqual({
        method: 'PATCH',
        path: '/companies/a',
        body: { hidden: true },
      }),
    )
  })

  it('US3_AS3_check_manually_tab', async () => {
    const user = userEvent.setup()
    const calls = renderPage((call) => {
      if (call.path === '/companies?filter=check_manually')
        return { items: [KEKA], next_cursor: null }
      return call.path.startsWith('/companies')
        ? { items: [ACME, KEKA], next_cursor: null }
        : undefined
    })
    await screen.findByRole('list', { name: 'Companies' })

    await user.click(screen.getByRole('tab', { name: 'Check manually' }))

    const list = await screen.findByRole('list', { name: 'Companies' })
    await waitFor(() => expect(within(list).getAllByRole('listitem')).toHaveLength(1))
    const item = within(list).getByRole('listitem')
    expect(item).toHaveTextContent('Keka')
    expect(item).toHaveTextContent('Last checked 5 Nov 2026')
    expect(within(item).getByRole('link', { name: /careers page/i })).toHaveAttribute(
      'href',
      'https://keka.example.com/careers',
    )
    expect(calls.some((c) => c.path === '/companies?filter=check_manually')).toBe(true)
  })

  it('edits_a_company_and_shows_field_errors', async () => {
    const user = userEvent.setup()
    const calls = renderPage((call) => {
      if (call.method === 'PATCH')
        return problem(422, 'Invalid', {
          errors: [{ field: 'name', message: 'The company needs a name.' }],
        })
      return call.path.startsWith('/companies') ? { items: [ACME], next_cursor: null } : undefined
    })

    await user.click(await screen.findByRole('button', { name: 'Edit Acme' }))
    await user.clear(screen.getByLabelText('Name'))
    await user.click(screen.getByRole('button', { name: 'Save' }))

    expect(await screen.findByText('The company needs a name.')).toBeInTheDocument()
    expect(calls.some((c) => c.method === 'PATCH' && c.path === '/companies/a')).toBe(true)
  })

  it('deleting_asks_first', async () => {
    const user = userEvent.setup()
    const calls = renderPage((call) => {
      if (call.method === 'DELETE') return new Response(null, { status: 204 })
      return call.path.startsWith('/companies') ? { items: [ACME], next_cursor: null } : undefined
    })

    await user.click(await screen.findByRole('button', { name: 'Delete Acme' }))
    expect(calls.some((c) => c.method === 'DELETE')).toBe(false)
    await user.click(screen.getByRole('button', { name: 'Yes, delete' }))

    await waitFor(() => expect(calls).toContainEqual({ method: 'DELETE', path: '/companies/a' }))
  })
})
