import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
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
    has_application: false,
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
      <MemoryRouter>
        <CompaniesPage />
      </MemoryRouter>
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
    expect(acme).toHaveTextContent('Pune') // its own Location column
    expect(acme).not.toHaveTextContent('Job board') // the board status is in the details
    expect(keka).not.toHaveTextContent('Check manually')
  })

  it('the board status and every other detail show when a row is expanded', async () => {
    const user = userEvent.setup()
    renderPage((call) =>
      call.path.startsWith('/companies')
        ? {
            items: [
              {
                ...ACME,
                website: 'https://acme.example.com',
                last_checked_at: '2026-11-05T09:00:00Z',
                last_check_result: 'ok',
              },
            ],
          }
        : undefined,
    )
    const row = await screen.findByRole('listitem', { name: 'Acme' })
    const toggle = within(row).getByRole('button', { name: 'Details for Acme' })
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    expect(within(row).queryByRole('region', { name: 'Details for Acme' })).toBeNull()

    await user.click(toggle)

    expect(toggle).toHaveAttribute('aria-expanded', 'true')
    const details = within(row).getByRole('region', { name: 'Details for Acme' })
    expect(details).toHaveTextContent('Job board')
    expect(details).toHaveTextContent('lever')
    expect(details).toHaveTextContent('Pune')
    expect(details).toHaveTextContent('Built-in list')
    expect(details).toHaveTextContent('Last checked 5 Nov 2026')
    expect(within(details).getByRole('link', { name: /acme\.example\.com$/ })).toHaveAttribute(
      'href',
      'https://acme.example.com',
    )
    expect(within(details).getByRole('link', { name: /acme\.example\.com\/careers/ })).toBeTruthy()
  })

  it('an icon opens the careers page in a new tab, and a company without one has none', async () => {
    renderPage((call) =>
      call.path.startsWith('/companies')
        ? { items: [ACME, company('n', 'Nolink', { careers_url: null })] }
        : undefined,
    )
    const acme = await screen.findByRole('listitem', { name: 'Acme' })

    const link = within(acme).getByRole('link', { name: 'Open Acme careers page' })
    expect(link).toHaveAttribute('href', 'https://acme.example.com/careers')
    expect(link).toHaveAttribute('target', '_blank')
    expect(link).toHaveAttribute('rel', 'noreferrer noopener')
    expect(link).toHaveAttribute('title', 'Careers page')
    const nolink = screen.getByRole('listitem', { name: 'Nolink' })
    expect(within(nolink).queryByRole('link', { name: /careers page/i })).toBeNull()
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
    const busy = company('b', 'Busy', {
      contact_count: 2,
      has_note: true,
      note_preview: 'Spoke to HR on Monday.',
    })
    const quiet = company('q', 'Quiet')
    renderPage((call) =>
      call.path.startsWith('/companies') ? { items: [busy, quiet], next_cursor: null } : undefined,
    )

    const [busyRow, quietRow] = within(
      await screen.findByRole('list', { name: 'Companies' }),
    ).getAllByRole('listitem')

    expect(busyRow).toHaveTextContent('2 contacts')
    expect(busyRow).toHaveTextContent('Spoke to HR on Monday.')
    expect(quietRow).toHaveTextContent('0 contacts')
    expect(quietRow).not.toHaveTextContent('Spoke to HR')
  })

  it('a row is one line of name, counts, note and icon actions with tooltips', async () => {
    renderPage((call) =>
      call.path.startsWith('/companies')
        ? { items: [company('b', 'Busy', { has_note: true, note_preview: 'Call back Friday' })] }
        : undefined,
    )
    const row = await screen.findByRole('listitem', { name: 'Busy' })

    expect(within(row).getByTitle('Call back Friday')).toBeInTheDocument() // the note, in full
    for (const [name, title] of [
      ['Details for Busy', 'Details'],
      ['Hide Busy', 'Hide'],
      ['Edit Busy', 'Edit'],
      ['Delete Busy', 'Delete'],
    ]) {
      const button = within(row).getByRole('button', { name })
      expect(button).toHaveAttribute('title', title)
      expect(button.querySelector('svg')).not.toBeNull() // an icon, not a text button
      expect(button).toHaveTextContent('')
    }
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

    await user.click(await screen.findByRole('button', { name: 'Details for Busy' }))

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

  describe('applications', () => {
    const busy = company('b', 'Busy', { has_application: true })
    const quiet = company('q', 'Quiet')
    const talked = company('t', 'Talked', { contact_count: 2 })
    const all = (call: Call) =>
      call.path.startsWith('/companies') ? { items: [quiet, busy, talked] } : undefined
    const rowOf = (name: string) => screen.getByRole('listitem', { name })
    const names = () =>
      within(screen.getByRole('list', { name: 'Companies' }))
        .getAllByRole('heading', { level: 2 })
        .map((h) => h.textContent)

    it('the row says Applied only for a company where there is an application', async () => {
      renderPage(all)
      await screen.findByRole('list', { name: 'Companies' })

      expect(within(rowOf('Busy')).getByText('Applied')).toBeInTheDocument()
      expect(within(rowOf('Quiet')).queryByText('Applied')).toBeNull()
    })

    it('open roles are not shown anywhere', async () => {
      const user = userEvent.setup()
      renderPage(all)
      await screen.findByRole('list', { name: 'Companies' })
      await user.click(within(rowOf('Busy')).getByRole('button', { name: 'Details for Busy' }))

      expect(screen.queryByText(/open roles/i)).toBeNull()
      expect(screen.queryByText(/not searched yet/i)).toBeNull()
      expect(screen.queryByRole('option', { name: /openings/i })).toBeNull()
    })

    it('the expanded details say whether there is an application', async () => {
      const user = userEvent.setup()
      renderPage(all)
      await screen.findByRole('list', { name: 'Companies' })

      await user.click(within(rowOf('Busy')).getByRole('button', { name: 'Details for Busy' }))
      await user.click(within(rowOf('Quiet')).getByRole('button', { name: 'Details for Quiet' }))

      expect(
        within(screen.getByRole('region', { name: 'Details for Busy' })).getByText(
          'You have applied to a job here',
        ),
      ).toBeInTheDocument()
      expect(
        within(screen.getByRole('region', { name: 'Details for Quiet' })).getByText(
          'No application',
        ),
      ).toBeInTheDocument()
    })

    it('filter_by_has_an_application_shows_only_that_company', async () => {
      const user = userEvent.setup()
      renderPage(all)
      await screen.findByRole('list', { name: 'Companies' })

      await user.selectOptions(screen.getByLabelText('Show'), 'applied')

      expect(names()).toEqual(['Busy'])
    })

    it('review: a filter that hides everything says so, not that there are no companies', async () => {
      const user = userEvent.setup()
      renderPage((call) =>
        call.path.startsWith('/companies') && call.method === 'GET'
          ? { items: [company('a', 'Acme')] }
          : undefined,
      )
      await screen.findByRole('list', { name: 'Companies' })

      await user.selectOptions(screen.getByLabelText('Show'), 'applied')

      expect(screen.getByText('No companies match this filter.')).toBeInTheDocument()
      expect(screen.queryByText(/No companies yet/)).toBeNull()
    })

    it('FR020_filter_by_has_contacts', async () => {
      const user = userEvent.setup()
      renderPage(all)
      await screen.findByRole('list', { name: 'Companies' })

      await user.selectOptions(screen.getByLabelText('Show'), 'contacts')

      expect(names()).toEqual(['Talked'])
    })

    it('sort_by_applied_from_the_header_puts_applied_companies_first_then_reverses', async () => {
      const user = userEvent.setup()
      renderPage(all)
      await screen.findByRole('list', { name: 'Companies' })

      await user.click(screen.getByRole('button', { name: /Sort by applied/ }))
      expect(names()[0]).toBe('Busy')

      await user.click(screen.getByRole('button', { name: /Sort by applied/ }))
      expect(names().at(-1)).toBe('Busy')
    })

    it('sorting_by_contacts_puts_the_most_contacts_first', async () => {
      const user = userEvent.setup()
      renderPage(all)
      await screen.findByRole('list', { name: 'Companies' })

      await user.click(screen.getByRole('button', { name: /Sort by contacts/ }))

      expect(names()[0]).toBe('Talked')
    })
  })

  describe('company site and careers page', () => {
    const acme = company('a', 'Acme', { website: 'https://acme.example.com' })
    const nosite = company('n', 'Nosite', { website: null, careers_url: null })
    const list = (call: Call) =>
      call.path.startsWith('/companies') ? { items: [acme, nosite] } : undefined

    it('the company name opens the company site in a new tab', async () => {
      renderPage(list)
      const row = await screen.findByRole('listitem', { name: 'Acme' })

      const link = within(row).getByRole('link', { name: 'Acme' })

      expect(link).toHaveAttribute('href', 'https://acme.example.com')
      expect(link).toHaveAttribute('target', '_blank')
      expect(link).toHaveAttribute('rel', 'noreferrer noopener')
      expect(within(row).getByRole('heading', { level: 2 })).toHaveTextContent('Acme')
    })

    it('a company with no website is plain text, not a link', async () => {
      renderPage(list)
      const row = await screen.findByRole('listitem', { name: 'Nosite' })

      expect(within(row).queryByRole('link')).toBeNull()
      expect(within(row).getByRole('heading', { level: 2 })).toHaveTextContent('Nosite')
    })

    it('there is an icon for the company site and another for the careers page', async () => {
      renderPage(list)
      const row = await screen.findByRole('listitem', { name: 'Acme' })

      const site = within(row).getByRole('link', { name: 'Open Acme website' })
      expect(site).toHaveAttribute('href', 'https://acme.example.com')
      expect(site).toHaveAttribute('title', 'Company website')
      expect(site).toHaveAttribute('target', '_blank')
      const careers = within(row).getByRole('link', { name: 'Open Acme careers page' })
      expect(careers).toHaveAttribute('href', 'https://acme.example.com/careers')
      expect(careers).toHaveAttribute('title', 'Careers page')
      expect(site.querySelector('svg')).not.toBeNull()
      expect(site.querySelector('svg')?.outerHTML).not.toEqual(
        careers.querySelector('svg')?.outerHTML,
      ) // two different icons
    })

    it('a missing link leaves no icon', async () => {
      renderPage(list)
      const row = await screen.findByRole('listitem', { name: 'Nosite' })

      expect(within(row).queryByRole('link', { name: /website/i })).toBeNull()
      expect(within(row).queryByRole('link', { name: /careers page/i })).toBeNull()
    })

    it('FR023 the website is a second line under the name', async () => {
      renderPage(list)
      const row = await screen.findByRole('listitem', { name: 'Acme' })

      const host = within(row).getByText('acme.example.com')

      expect(host).toHaveClass('text-xs')
      expect(host).toHaveClass('text-muted-small')
      expect(within(row).getByRole('heading', { level: 2 })).not.toContainElement(host)
    })

    it('FR023 no second line without a website', async () => {
      renderPage(list)
      const row = await screen.findByRole('listitem', { name: 'Nosite' })

      expect(row.querySelector('[data-testid="company-host"]')).toBeNull()
    })

    it('FR023 a row is a plain line with a bottom divider, not a card', async () => {
      renderPage(list)
      const row = await screen.findByRole('listitem', { name: 'Acme' })

      expect(row).toHaveClass('border-b')
      expect(row).not.toHaveClass('rounded-lg')
      expect(row).not.toHaveClass('bg-surface')
    })

    it('FR024 action icons keep their own colours', async () => {
      renderPage(list)
      const row = await screen.findByRole('listitem', { name: 'Acme' })

      const tone = (name: string, colour: string) =>
        expect(within(row).getByRole(name.startsWith('Open') ? 'link' : 'button', { name })).toHaveClass(
          colour,
        )
      tone('Details for Acme', 'text-slate-300')
      tone('Open Acme website', 'text-orange-300')
      tone('Open Acme careers page', 'text-violet-300')
      tone('Hide Acme', 'text-yellow-300')
      tone('Edit Acme', 'text-emerald-300')
      tone('Delete Acme', 'text-rose-300')
    })

    it('FR024 the row hover tint is see-through', async () => {
      renderPage(list)
      const row = await screen.findByRole('listitem', { name: 'Acme' })

      expect(row).toHaveClass('hover:bg-[#9c4f37]/25')
    })

    it('FR023 the header is plain title case with a bottom divider', async () => {
      renderPage(list)
      await screen.findByRole('listitem', { name: 'Acme' })

      const button = screen.getByRole('button', { name: /^Sort by company/ })
      const header = button.parentElement as HTMLElement

      expect(header).toHaveClass('border-b')
      expect(header).not.toHaveClass('bg-slate-200/10')
      expect(button).not.toHaveClass('uppercase')
    })
  })

  describe('the table header', () => {
    const rows = (call: Call) =>
      call.path.startsWith('/companies')
        ? {
            items: [
              company('1', 'Bravo', { city: 'Pune', note_preview: 'zeta', has_note: true }),
              company('2', 'Alpha', { city: 'Mumbai' }),
              company('3', 'Charlie', { city: 'Chennai', note_preview: 'alpha', has_note: true }),
            ],
          }
        : undefined
    const names = () =>
      within(screen.getByRole('list', { name: 'Companies' }))
        .getAllByRole('heading', { level: 2 })
        .map((h) => h.textContent)

    it('starts by company name, and a second click on it reverses the order', async () => {
      const user = userEvent.setup()
      renderPage(rows)
      await screen.findByRole('list', { name: 'Companies' })
      expect(names()).toEqual(['Alpha', 'Bravo', 'Charlie'])

      await user.click(screen.getByRole('button', { name: /Sort by company/ }))

      expect(names()).toEqual(['Charlie', 'Bravo', 'Alpha'])
    })

    it('a search box finds a company by name or city as you type', async () => {
      const user = userEvent.setup()
      renderPage(rows)
      await screen.findByRole('list', { name: 'Companies' })
      const box = screen.getByRole('searchbox', { name: 'Search companies' })

      await user.type(box, 'ALP')
      expect(names()).toEqual(['Alpha']) // any case

      await user.clear(box)
      await user.type(box, 'chennai')
      expect(names()).toEqual(['Charlie']) // by city too

      await user.clear(box)
      await user.type(box, 'zzz')
      expect(screen.getByText('No companies match this filter.')).toBeInTheDocument()

      await user.clear(box)
      expect(names()).toEqual(['Alpha', 'Bravo', 'Charlie'])
    })

    it('searching keeps the chosen sort order', async () => {
      const user = userEvent.setup()
      renderPage(rows)
      await screen.findByRole('list', { name: 'Companies' })
      await user.click(screen.getByRole('button', { name: /Sort by company/ })) // Z to A

      await user.type(screen.getByRole('searchbox', { name: 'Search companies' }), 'a')

      expect(names()).toEqual(['Charlie', 'Bravo', 'Alpha']) // all three have an a
    })

    it('sorts by location, and by note text, with empty values last', async () => {
      const user = userEvent.setup()
      renderPage(rows)
      await screen.findByRole('list', { name: 'Companies' })

      await user.click(screen.getByRole('button', { name: /Sort by location/ }))
      expect(names()).toEqual(['Charlie', 'Alpha', 'Bravo']) // Chennai, Mumbai, Pune

      await user.click(screen.getByRole('button', { name: /Sort by note/ }))
      expect(names()).toEqual(['Charlie', 'Bravo', 'Alpha']) // alpha, zeta, then no note
    })

    it('says which column is sorted and which way', async () => {
      const user = userEvent.setup()
      renderPage(rows)
      await screen.findByRole('list', { name: 'Companies' })

      expect(screen.getByRole('button', { name: 'Sort by company, now A to Z' })).toBeTruthy()
      await user.click(screen.getByRole('button', { name: /Sort by location/ }))

      expect(screen.getByRole('button', { name: 'Sort by location, now A to Z' })).toBeTruthy()
      expect(screen.getByRole('button', { name: 'Sort by company' })).toBeTruthy()
    })
  })

  describe('the toolbar', () => {
    const list = (call: Call) =>
      call.path.startsWith('/companies') ? { items: [ACME], next_cursor: null } : undefined

    it('FR025 toolbar buttons have icons', async () => {
      renderPage(list)
      await screen.findByRole('listitem', { name: 'Acme' })

      const filter = screen.getByRole('form', { name: 'Company filters' })
      expect(filter.querySelector('svg')).not.toBeNull() // Show: eye icon
      for (const name of ['Add a company', 'Check manually']) {
        const button = screen.getByRole(name === 'Check manually' ? 'tab' : 'button', { name })
        expect(button.querySelector('svg')).not.toBeNull()
        expect(button).toHaveClass('bg-[#243044]')
        expect(button).toHaveClass('text-[#f0a35e]')
      }
    })

    it('FR025 check manually is selectable', async () => {
      const user = userEvent.setup()
      renderPage(list)
      await screen.findByRole('listitem', { name: 'Acme' })
      const all = screen.getByRole('tab', { name: 'All companies' })
      const manual = screen.getByRole('tab', { name: 'Check manually' })
      expect(all).toHaveAttribute('aria-selected', 'true')

      await user.click(manual)

      expect(manual).toHaveAttribute('aria-selected', 'true')
      expect(all).toHaveAttribute('aria-selected', 'false')
    })
  })
})
