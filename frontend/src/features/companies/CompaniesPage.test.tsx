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
    contact_count: 0,
    has_note: false,
    openings: null,
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

  it('US2 AS1 row shows counts and note marker', async () => {
    const busy = company('b', 'Busy', { contact_count: 2, has_note: true })
    const quiet = company('q', 'Quiet')
    renderPage((call) =>
      call.path.startsWith('/companies') ? { items: [busy, quiet], next_cursor: null } : undefined,
    )

    const [busyRow, quietRow] = within(
      await screen.findByRole('list', { name: 'Companies' }),
    ).getAllByRole('listitem')

    expect(busyRow).toHaveTextContent('2 contacts')
    expect(busyRow).toHaveTextContent('Has a note')
    expect(quietRow).toHaveTextContent('0 contacts')
    expect(quietRow).not.toHaveTextContent('Has a note')
  })

  it('SC004 contacts reachable in two clicks', async () => {
    const user = userEvent.setup()
    const busy = company('b', 'Busy', { contact_count: 1 })
    renderPage((call) => {
      if (call.path === '/companies/b/contacts')
        return {
          items: [
            {
              id: 'k1',
              company_id: 'b',
              name: 'Jane Example',
              role: 'Recruiter',
              linkedin_url: null,
              email: null,
              phone: null,
              confidence: null,
              note: null,
              source: 'typed',
              updated_at: '2026-11-09T09:00:00Z',
            },
          ],
          note: null,
        }
      return call.path.startsWith('/companies') ? { items: [busy], next_cursor: null } : undefined
    })

    await user.click(await screen.findByRole('button', { name: 'Contacts and note for Busy' }))

    expect(await screen.findByText('Jane Example')).toBeInTheDocument()
  })

  it('FR023 delete confirmation states the contact count', async () => {
    const user = userEvent.setup()
    const mine = company('m', 'Mine', {
      origin: 'user',
      contact_count: 3,
      has_note: true,
    })
    renderPage((call) =>
      call.path.startsWith('/companies') ? { items: [mine], next_cursor: null } : undefined,
    )

    await user.click(await screen.findByRole('button', { name: 'Delete Mine' }))

    expect(screen.getByText(/3 contacts and the note will be deleted too/)).toBeInTheDocument()
  })

  it('FR023 a built-in company keeps its contacts when deleted', async () => {
    const user = userEvent.setup()
    const shipped = company('s', 'Shipped', { contact_count: 3 })
    renderPage((call) =>
      call.path.startsWith('/companies') ? { items: [shipped], next_cursor: null } : undefined,
    )

    await user.click(await screen.findByRole('button', { name: 'Delete Shipped' }))

    expect(screen.queryByText(/contacts and the note will be deleted/)).toBeNull()
    expect(screen.getByText(/will not come back with the shipped list/)).toBeInTheDocument()
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
