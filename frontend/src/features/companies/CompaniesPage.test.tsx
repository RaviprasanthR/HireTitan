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
    pipeline: null,
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

  it('test_FR016_companies_rows_are_cards', async () => {
    renderPage((call) =>
      call.path.startsWith('/companies') ? { items: [ACME, KEKA], next_cursor: null } : undefined,
    )
    const list = await screen.findByRole('list', { name: 'Companies' })
    for (const row of within(list).getAllByRole('listitem')) {
      // below 768px each company is a card (theme.css `ht-list-card`); names wrap there
      expect(row).toHaveClass('ht-list-card')
      expect(row.querySelector('h2')).toHaveClass('md:truncate')
      expect(row.querySelector('h2')).not.toHaveClass('truncate')
    }
    const css = (await import('node:fs')).readFileSync('src/theme/theme.css', 'utf8')
    expect(css.slice(css.indexOf('@media (max-width: 767.98px)'))).toContain('.ht-list-card')
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
    const toggle = within(row).getByRole('button', {
      name: 'Details for Acme',
    })
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    expect(within(row).queryByRole('region', { name: 'Details for Acme' })).toBeNull()

    await user.click(toggle)

    expect(toggle).toHaveAttribute('aria-expanded', 'true')
    const details = within(row).getByRole('region', {
      name: 'Details for Acme',
    })
    expect(details).toHaveTextContent('Job board')
    expect(details).toHaveTextContent('lever')
    expect(details).toHaveTextContent('Pune')
    expect(details).toHaveTextContent('Built-in list')
    expect(details).toHaveTextContent('Last checked 5 Nov 2026')
    expect(within(details).getByRole('link', { name: /acme\.example\.com$/ })).toHaveAttribute(
      'href',
      'https://acme.example.com',
    )
    expect(
      within(details).getByRole('link', {
        name: /acme\.example\.com\/careers/,
      }),
    ).toBeTruthy()
  })

  it('an icon opens the company site in a new tab, and a company without one has none', async () => {
    renderPage((call) =>
      call.path.startsWith('/companies')
        ? {
            items: [
              company('a', 'Acme', { website: 'https://acme.example.com' }),
              company('n', 'Nolink', { website: null }),
            ],
          }
        : undefined,
    )
    const acme = await screen.findByRole('listitem', { name: 'Acme' })

    const link = within(acme).getByRole('link', {
      name: 'Open Acme website',
    })
    expect(link).toHaveAttribute('href', 'https://acme.example.com')
    expect(link).toHaveAttribute('target', '_blank')
    expect(link).toHaveAttribute('rel', 'noreferrer noopener')
    expect(link).toHaveAttribute('title', 'Company site')
    const nolink = screen.getByRole('listitem', { name: 'Nolink' })
    expect(within(nolink).queryByRole('link', { name: /website/i })).toBeNull()
  })

  it('there is no Hide button; a company hidden before can be searched again from Edit', async () => {
    const user = userEvent.setup()
    const hidden = { ...ACME, hidden: true }
    const calls = renderPage((call) => {
      if (call.method === 'PATCH') return ACME
      return call.path.startsWith('/companies') ? { items: [hidden], next_cursor: null } : undefined
    })

    await user.click(await screen.findByRole('button', { name: 'Edit Acme' }))
    expect(screen.queryByRole('button', { name: /^Hide / })).toBeNull()
    await user.click(screen.getByRole('button', { name: 'Search this company again' }))

    await waitFor(() =>
      expect(calls).toContainEqual({
        method: 'PATCH',
        path: '/companies/a',
        body: { hidden: false },
      }),
    )
  })

  it('a click on the row opens its details and a second click closes them', async () => {
    const user = userEvent.setup()
    renderPage((call) =>
      call.path.startsWith('/companies')
        ? { items: [{ ...ACME, city: 'Pune' }], next_cursor: null }
        : undefined,
    )
    const row = await screen.findByRole('listitem', { name: 'Acme' })

    await user.click(within(row).getByText('Pune'))
    expect(await screen.findByRole('region', { name: 'Details for Acme' })).toBeInTheDocument()
    expect(within(row).getByRole('button', { name: 'Details for Acme' })).toHaveAttribute(
      'aria-expanded',
      'true',
    )

    await user.click(within(row).getAllByText('Pune').at(0) as HTMLElement)
    expect(screen.queryByRole('region', { name: 'Details for Acme' })).toBeNull()
  })

  it("the edit form's own buttons do not open or close the row", async () => {
    const user = userEvent.setup()
    renderPage((call) =>
      call.path.startsWith('/companies') ? { items: [ACME], next_cursor: null } : undefined,
    )
    const row = await screen.findByRole('listitem', { name: 'Acme' })

    await user.click(within(row).getByRole('button', { name: 'Edit Acme' }))

    expect(screen.queryByRole('region', { name: 'Details for Acme' })).toBeNull()
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
        ? {
            items: [
              company('b', 'Busy', {
                has_note: true,
                note_preview: 'Call back Friday',
              }),
            ],
          }
        : undefined,
    )
    const row = await screen.findByRole('listitem', { name: 'Busy' })

    expect(within(row).getByTitle('Call back Friday')).toBeInTheDocument() // the note, in full
    for (const [name, title] of [['Edit Busy', 'Edit']]) {
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

    await user.click(await screen.findByRole('button', { name: 'Edit Mine' }))
    await user.click(screen.getByRole('button', { name: 'Delete Mine' }))

    expect(screen.getByText(/3 contacts and the note will be deleted too/)).toBeInTheDocument()
  })

  it('FR023 a built-in company keeps its contacts when deleted', async () => {
    const user = userEvent.setup()
    const shipped = company('s', 'Shipped', { contact_count: 3 })
    renderPage((call) =>
      call.path.startsWith('/companies') ? { items: [shipped], next_cursor: null } : undefined,
    )

    await user.click(await screen.findByRole('button', { name: 'Edit Shipped' }))
    await user.click(screen.getByRole('button', { name: 'Delete Shipped' }))

    expect(screen.queryByText(/contacts and the note will be deleted/)).toBeNull()
    expect(screen.getByText(/will not come back with the shipped list/)).toBeInTheDocument()
  })

  it('deleting_asks_first', async () => {
    const user = userEvent.setup()
    const calls = renderPage((call) => {
      if (call.method === 'DELETE') return new Response(null, { status: 204 })
      return call.path.startsWith('/companies') ? { items: [ACME], next_cursor: null } : undefined
    })

    await user.click(await screen.findByRole('button', { name: 'Edit Acme' }))
    await user.click(screen.getByRole('button', { name: 'Delete Acme' }))
    expect(calls.some((c) => c.method === 'DELETE')).toBe(false)
    await user.click(screen.getByRole('button', { name: 'Yes, delete' }))

    await waitFor(() => expect(calls).toContainEqual({ method: 'DELETE', path: '/companies/a' }))
  })

  describe('applications', () => {
    const busy = company('b', 'Busy', { pipeline: 'applied' })
    const asked = company('i', 'Asked', { pipeline: 'inquired' })
    const quiet = company('q', 'Quiet')
    const talked = company('t', 'Talked', { contact_count: 2 })
    const all = (call: Call) =>
      call.path.startsWith('/companies') ? { items: [quiet, asked, busy, talked] } : undefined
    const rowOf = (name: string) => screen.getByRole('listitem', { name })
    const names = () =>
      within(screen.getByRole('list', { name: 'Companies' }))
        .getAllByRole('heading', { level: 2 })
        .map((h) => h.textContent)

    it('the row says Applied only for a company where there is an application', async () => {
      renderPage(all)
      await screen.findByRole('list', { name: 'Companies' })

      expect(within(rowOf('Busy')).getByText('Applied')).toHaveAttribute('data-stage', 'applied')
      expect(within(rowOf('Quiet')).queryByText('Applied')).toBeNull()
    })

    it('FR009 inquired chip', async () => {
      renderPage(all)
      await screen.findByRole('list', { name: 'Companies' })

      const chip = within(rowOf('Asked')).getByText('Inquired')

      expect(chip).toBeInTheDocument()
      expect(within(rowOf('Asked')).queryByText('Applied')).toBeNull()
      const applied = within(rowOf('Busy')).getByText('Applied')
      expect(chip).toHaveAttribute('data-stage', 'inquired') // each in its own stage colour
      expect(applied).toHaveAttribute('data-stage', 'applied')
    })

    it('FR009 applied wins over inquired', async () => {
      // the server sends one value per company: applied if any job there is applied
      renderPage((call) =>
        call.path.startsWith('/companies')
          ? { items: [company('x', 'Both', { pipeline: 'applied' })] }
          : undefined,
      )
      await screen.findByRole('list', { name: 'Companies' })

      expect(within(rowOf('Both')).getByText('Applied')).toBeInTheDocument()
      expect(within(rowOf('Both')).queryByText('Inquired')).toBeNull()
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

    it('the expanded details say how far the pipeline has got', async () => {
      const user = userEvent.setup()
      renderPage(all)
      await screen.findByRole('list', { name: 'Companies' })

      await user.click(within(rowOf('Busy')).getByRole('button', { name: 'Details for Busy' }))
      await user.click(
        within(rowOf('Asked')).getByRole('button', {
          name: 'Details for Asked',
        }),
      )
      await user.click(
        within(rowOf('Quiet')).getByRole('button', {
          name: 'Details for Quiet',
        }),
      )

      expect(
        within(screen.getByRole('region', { name: 'Details for Busy' })).getByText(
          'You have applied to a job here',
        ),
      ).toBeInTheDocument()
      expect(
        within(screen.getByRole('region', { name: 'Details for Asked' })).getByText(
          'You have asked about a job here',
        ),
      ).toBeInTheDocument()
      expect(
        within(screen.getByRole('region', { name: 'Details for Quiet' })).getByText(
          'Nothing in your pipeline here',
        ),
      ).toBeInTheDocument()
    })

    it('FR009 sort applied then inquired, then the rest, and reverses', async () => {
      const user = userEvent.setup()
      renderPage(all)
      await screen.findByRole('list', { name: 'Companies' })

      await user.click(screen.getByRole('button', { name: /Sort by pipeline/ }))
      expect(names().slice(0, 2)).toEqual(['Busy', 'Asked'])

      await user.click(screen.getByRole('button', { name: /Sort by pipeline/ }))
      expect(names().slice(-2)).toEqual(['Asked', 'Busy'])
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
    const siteOnly = company('s', 'Siteonly', {
      website: 'https://siteonly.example.com',
      careers_url: null,
    })
    const list = (call: Call) =>
      call.path.startsWith('/companies') ? { items: [acme, nosite, siteOnly] } : undefined

    it('the company name opens the row; the careers page is linked in the details', async () => {
      const user = userEvent.setup()
      renderPage(list)
      const row = await screen.findByRole('listitem', { name: 'Acme' })

      expect(within(row).queryByRole('link', { name: 'Acme' })).toBeNull()
      expect(within(row).getByRole('heading', { level: 2 })).toHaveTextContent('Acme')
      await user.click(within(row).getByRole('button', { name: 'Details for Acme' }))
      const details = screen.getByRole('region', { name: 'Details for Acme' })
      const careers = within(details).getByRole('link', {
        name: 'acme.example.com/careers',
      })
      expect(careers).toHaveAttribute('target', '_blank')
    })

    it('only the company site has an icon on the row', async () => {
      renderPage(list)
      const row = await screen.findByRole('listitem', { name: 'Acme' })

      expect(within(row).queryByRole('link', { name: 'Open Acme careers page' })).toBeNull()
      const site = within(row).getByRole('link', { name: 'Open Acme website' })
      expect(site).toHaveAttribute('href', 'https://acme.example.com')
      expect(site).toHaveAttribute('title', 'Company site')
      expect(site).toHaveAttribute('target', '_blank')
      expect(site.querySelector('svg')).not.toBeNull()
    })

    it('a company with only a website still has the icon', async () => {
      renderPage(list)
      const row = await screen.findByRole('listitem', { name: 'Siteonly' })

      expect(within(row).getByRole('link', { name: 'Open Siteonly website' })).toHaveAttribute(
        'href',
        'https://siteonly.example.com',
      )
    })

    it('a missing link leaves no icon', async () => {
      renderPage(list)
      const row = await screen.findByRole('listitem', { name: 'Nosite' })

      expect(within(row).queryByRole('link', { name: /website/i })).toBeNull()
      expect(within(row).queryByRole('link', { name: /careers page/i })).toBeNull()
    })

    it('the row shows no address under the name, the site is behind its icon', async () => {
      renderPage(list)
      const row = await screen.findByRole('listitem', { name: 'Acme' })

      expect(within(row).queryByText('acme.example.com')).not.toBeInTheDocument()
      expect(row.querySelector('[data-testid="company-host"]')).toBeNull()
      expect(within(row).getByRole('link', { name: 'Open Acme website' })).toBeInTheDocument()
    })

    it('FR023 a row is a plain line with a divider and square corners, not a card', async () => {
      renderPage(list)
      const row = await screen.findByRole('listitem', { name: 'Acme' })

      expect(row).toHaveClass('after:bg-border') // the divider
      expect(row).not.toHaveClass('bg-surface')
    })

    it('FR024 action icons keep their own colours', async () => {
      renderPage(list)
      const row = await screen.findByRole('listitem', { name: 'Acme' })

      const tone = (name: string, colour: string) =>
        expect(
          within(row).getByRole(name.startsWith('Open') ? 'link' : 'button', {
            name,
          }),
        ).toHaveClass(colour)
      tone('Open Acme website', 'text-link')
      tone('Edit Acme', 'text-success')
      expect(within(row).queryByRole('button', { name: /^Hide / })).toBeNull()
    })

    it('an opened row has no orange tint, so the details are not highlighted', async () => {
      const user = userEvent.setup()
      renderPage(list)
      const row = await screen.findByRole('listitem', { name: 'Acme' })
      expect(row).toHaveClass('hover:bg-raised') // closed: the tint under the pointer

      await user.click(within(row).getByRole('button', { name: 'Details for Acme' }))

      expect(row).not.toHaveClass('hover:bg-raised')
      await user.click(within(row).getByRole('button', { name: 'Details for Acme' }))
      expect(row).toHaveClass('hover:bg-raised') // closed again: the tint is back
    })

    it('a row being edited or asked about deleting has no orange tint', async () => {
      const user = userEvent.setup()
      renderPage(list)
      const row = await screen.findByRole('listitem', { name: 'Acme' })

      await user.click(within(row).getByRole('button', { name: 'Edit Acme' }))
      expect(row).not.toHaveClass('hover:bg-raised')
      await user.click(within(row).getByRole('button', { name: 'Cancel' }))
      expect(row).toHaveClass('hover:bg-raised')

      await user.click(within(row).getByRole('button', { name: 'Edit Acme' }))
      await user.click(within(row).getByRole('button', { name: 'Delete Acme' }))
      expect(row).not.toHaveClass('hover:bg-raised')
    })

    it('the edit form saves in green, cancels in orange; the delete question is red', async () => {
      const user = userEvent.setup()
      renderPage(list)
      const row = await screen.findByRole('listitem', { name: 'Acme' })

      await user.click(within(row).getByRole('button', { name: 'Edit Acme' }))
      expect(within(row).getByRole('button', { name: 'Save' })).toHaveClass('ht-success-button')
      expect(within(row).getByRole('button', { name: 'Cancel' })).toHaveClass('ht-cancel-button')
      await user.click(within(row).getByRole('button', { name: 'Cancel' }))

      await user.click(within(row).getByRole('button', { name: 'Edit Acme' }))
      await user.click(within(row).getByRole('button', { name: 'Delete Acme' }))
      expect(within(row).getByRole('button', { name: 'Yes, delete' })).toHaveClass(
        'ht-danger-button',
      )
      expect(within(row).getByRole('button', { name: 'Keep it' })).toHaveClass('ht-cancel-button')
    })

    it('the opened details are accent cards, like Preferences and Search rules', async () => {
      const user = userEvent.setup()
      renderPage(list)
      const row = await screen.findByRole('listitem', { name: 'Acme' })

      await user.click(within(row).getByRole('button', { name: 'Details for Acme' }))

      const details = await within(row).findByRole('region', {
        name: 'Details for Acme',
      })
      for (const [title, shows] of [
        ['Company', 'Location'],
        ['Job source', 'Job board'],
      ] as const) {
        const heading = within(details).getByRole('heading', { name: title })
        const card = heading.closest('.ht-detail-card') as HTMLElement
        expect(card).not.toBeNull()
        expect(card).toHaveTextContent(shows)
      }
    })

    it('FR024 the row hover tint is see-through', async () => {
      renderPage(list)
      const row = await screen.findByRole('listitem', { name: 'Acme' })

      expect(row).toHaveClass('hover:bg-raised')
    })

    it('the header has the same look as the pipeline table header', async () => {
      renderPage(list)
      await screen.findByRole('listitem', { name: 'Acme' })

      const button = screen.getByRole('button', { name: /^Sort by company/ })
      const header = button.parentElement as HTMLElement

      expect(header).toHaveClass('ht-thead-row')
    })

    it('the rows are square like the In pipeline rows, so they fit under the header', async () => {
      renderPage(list)
      const row = await screen.findByRole('listitem', { name: 'Acme' })

      expect(row.className).not.toMatch(/rounded/)
    })
  })

  describe('the table header', () => {
    const rows = (call: Call) =>
      call.path.startsWith('/companies')
        ? {
            items: [
              company('1', 'Bravo', {
                city: 'Pune',
                note_preview: 'zeta',
                has_note: true,
              }),
              company('2', 'Alpha', { city: 'Mumbai' }),
              company('3', 'Charlie', {
                city: 'Chennai',
                note_preview: 'alpha',
                has_note: true,
              }),
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
      expect(screen.getByText('No companies match this search.')).toBeInTheDocument()

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

    it('FR025 there are no list tabs and no Show filter', async () => {
      renderPage(list)
      await screen.findByRole('listitem', { name: 'Acme' })

      expect(screen.queryAllByRole('tab')).toHaveLength(0)
      expect(screen.queryByLabelText('Show')).toBeNull()
      expect(screen.queryByRole('form', { name: 'Company filters' })).toBeNull()
    })

    it('FR025 the Add a company button is a filled chip with an icon', async () => {
      renderPage(list)
      await screen.findByRole('listitem', { name: 'Acme' })

      const button = screen.getByRole('button', { name: 'Add a company' })

      expect(button.querySelector('svg')).not.toBeNull()
      expect(button).toHaveClass('bg-raised')
      expect(button).toHaveClass('text-foreground')
    })

    it('FR026 Add a company opens a dialog over the list, and Cancel closes it', async () => {
      const user = userEvent.setup()
      renderPage(list)
      await screen.findByRole('listitem', { name: 'Acme' })
      expect(screen.queryByRole('dialog', { name: 'Add a company' })).toBeNull()

      await user.click(screen.getByRole('button', { name: 'Add a company' }))

      expect(screen.getByRole('dialog', { name: 'Add a company' })).toBeInTheDocument()
      expect(screen.getByRole('list', { name: 'Companies' })).toBeInTheDocument() // still behind it

      await user.click(screen.getByRole('button', { name: 'Cancel' }))

      expect(screen.queryByRole('dialog', { name: 'Add a company' })).toBeNull()
    })
  })
})
