import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { problem, stubApi } from '@/test/api'
import { UndoToast } from '@/features/jobs/UndoToast'
import { PipelinePage } from './PipelinePage'

function applied(id: string, title: string, day: string) {
  return {
    id,
    title: `${title} (Python) - Pune`,
    role: title,
    company_name: 'Acme',
    location_text: 'Pune, India',
    work_mode: 'remote',
    posted_at: null,
    first_seen_at: '2026-11-01T00:00:00Z',
    state: 'applied',
    restored: false,
    sources: [{ kind: 'company_board', url: 'https://jobs.example.com/1' }],
    decision: null,
    listed: false,
    applied_on: day,
    inquired_on: null,
  }
}

function inquired(id: string, title: string, day: string) {
  return {
    ...applied(id, title, day),
    state: 'inquired',
    applied_on: null,
    inquired_on: day,
  }
}

const SUMMARY = { total: 9, inquired: 3, applied: 2, scheduled: 2, cleared: 1, failed: 1 }

function renderPage(initial?: unknown[], summary: unknown = SUMMARY) {
  let rows = (initial as ReturnType<typeof applied>[] | undefined) ?? [
    applied('a', 'Newest', '2026-11-05'),
    inquired('b', 'Older', '2026-10-01'),
  ]
  const calls = stubApi((call) => {
    if (call.method === 'DELETE' && call.path === '/jobs/a/applied') {
      rows = rows.filter((row) => row.id !== 'a')
      return {
        ...applied('a', 'Newest', '2026-11-05'),
        state: 'explore',
        applied_on: null,
      }
    }
    if (call.path.startsWith('/jobs?')) return { items: rows, next_cursor: null }
    if (call.path === '/pipeline/summary') return summary
    return undefined
  })
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <MemoryRouter>
        <PipelinePage />
        <UndoToast />
      </MemoryRouter>
    </QueryClientProvider>,
  )
  return calls
}

afterEach(() => vi.unstubAllGlobals())

describe('PipelinePage', () => {
  it('shows the pipeline by status as a flow chart and a donut', async () => {
    renderPage()

    const flow = await screen.findByRole('list', { name: 'Your pipeline' })
    const steps = within(flow).getAllByRole('listitem')
    expect(steps.map((step) => step.textContent)).toEqual([
      expect.stringMatching(/^In pipeline9/),
      expect.stringMatching(/^Inquired3/),
      expect.stringMatching(/^Applied2/),
      expect.stringMatching(/^Interview scheduled2/),
      expect.stringMatching(/^Round cleared11 failed/),
    ])
    const donut = screen.getByRole('img', {
      name: '3 inquired, 2 applied, 2 interview scheduled, 1 round cleared, 1 failed',
    })
    expect(donut.querySelectorAll('[data-part]')).toHaveLength(5)
    expect(screen.getByTestId('donut-centre')).toHaveTextContent('9jobs in pipeline')
  })

  it('shows no chart while the pipeline is empty', async () => {
    renderPage([], { total: 0, inquired: 0, applied: 0, scheduled: 0, cleared: 0, failed: 0 })
    expect(await screen.findByText(/Nothing in your pipeline yet/)).toBeInTheDocument()
    expect(screen.queryByRole('list', { name: 'Your pipeline' })).not.toBeInTheDocument()
  })

  it('US1 AS2 pipeline lists applied and inquired', async () => {
    const calls = renderPage()

    const table = await screen.findByRole('table', { name: 'Pipeline jobs' })
    expect(
      within(table)
        .getAllByRole('columnheader')
        .map((header) => header.textContent),
    ).toEqual(['Company', 'Role', 'Date', 'Status', 'Resume', 'Source', ''])
    const [, newest, older] = within(table).getAllByRole('row')
    if (!newest || !older) throw new Error('expected two rows')
    expect(within(newest).getByRole('link', { name: 'Newest' })).toBeInTheDocument()
    expect(within(older).getByRole('link', { name: 'Older' })).toBeInTheDocument()
    expect(newest).toHaveTextContent('Acme')
    expect(newest).toHaveTextContent('5 Nov 2026')
    expect(newest).toHaveTextContent('Applied')
    expect(older).toHaveTextContent('Inquired')
    expect(older).toHaveTextContent('1 Oct 2026')
    expect(newest).toHaveTextContent('Company job board')
    expect(calls.some((call) => call.path.includes('list=pipeline'))).toBe(true)
  })

  it('expanding_a_row_shows_the_description', async () => {
    const user = userEvent.setup()
    stubApi((call) => {
      if (call.path === '/jobs/a')
        return {
          ...applied('a', 'Newest', '2026-11-05'),
          description: 'Build services with Python.',
          city: 'Pune',
          country: 'IN',
          skills_found: ['Python'],
          sources: [
            {
              kind: 'company_board',
              url: 'https://jobs.example.com/1',
              label: null,
            },
          ],
          decision_history: [],
          injection_flags: [],
        }
      if (call.path.startsWith('/jobs?'))
        return {
          items: [applied('a', 'Newest', '2026-11-05')],
          next_cursor: null,
        }
      return undefined
    })
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <PipelinePage />
        </MemoryRouter>
      </QueryClientProvider>,
    )
    const toggle = await screen.findByRole('button', {
      name: 'Details for Newest (Python) - Pune',
    })
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByText('Build services with Python.')).toBeNull()

    await user.click(toggle)

    expect(await screen.findByText('Build services with Python.')).toBeInTheDocument()
    expect(toggle).toHaveAttribute('aria-expanded', 'true')
    await user.click(toggle)
    expect(screen.queryByText('Build services with Python.')).toBeNull()
  })

  it('US1 AS1 row expands to the detail panel', async () => {
    const user = userEvent.setup()
    stubApi((call) => {
      if (call.path === '/jobs/a/interview')
        return {
          job_id: 'a',
          can_edit: true,
          can_add_round: true,
          contact: {
            name: 'Asha Rao',
            role: null,
            email: null,
            phone: null,
            linkedin_url: null,
          },
          source: { kind: 'hiring_firm', firm_name: 'TalentBridge' },
          rounds: [],
          status: { state: 'applied', round: null },
          resume: { state: 'none', resume_file_id: null, name: null, added_on: null },
        }
      if (call.path === '/jobs/a')
        return {
          ...applied('a', 'Newest', '2026-11-05'),
          description: 'Build services with Python.',
          city: 'Pune',
          country: 'IN',
          skills_found: [],
          sources: [
            {
              kind: 'company_board',
              url: 'https://jobs.example.com/1',
              label: null,
            },
          ],
          decision_history: [],
          injection_flags: [],
        }
      if (call.path.startsWith('/jobs?'))
        return {
          items: [applied('a', 'Newest', '2026-11-05')],
          next_cursor: null,
        }
      return undefined
    })
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <PipelinePage />
        </MemoryRouter>
      </QueryClientProvider>,
    )
    await user.click(
      await screen.findByRole('button', {
        name: 'Details for Newest (Python) - Pune',
      }),
    )

    expect(await screen.findByLabelText('Contact name')).toHaveValue('Asha Rao')
    expect(screen.getByLabelText('Firm name')).toHaveValue('TalentBridge')
    expect(screen.getByRole('radio', { name: 'Through a hiring firm' })).toBeChecked()
  })

  it('an opened row sets the location, description, sources and job page apart, with icons', async () => {
    const user = userEvent.setup()
    stubApi((call) => {
      if (call.path === '/jobs/a')
        return {
          ...applied('a', 'Newest', '2026-11-05'),
          description: 'Build services with Python.',
          sources: [
            {
              kind: 'company_board',
              url: 'https://jobs.example.com/1',
              label: null,
            },
          ],
          decision_history: [],
          injection_flags: [],
        }
      if (call.path.startsWith('/jobs?'))
        return {
          items: [applied('a', 'Newest', '2026-11-05')],
          next_cursor: null,
        }
      return undefined
    })
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <PipelinePage />
        </MemoryRouter>
      </QueryClientProvider>,
    )

    await user.click(
      await screen.findByRole('button', {
        name: 'Details for Newest (Python) - Pune',
      }),
    )

    const place = await screen.findByLabelText('Location')
    expect(place).toHaveTextContent('Pune, India')
    expect(place.querySelector('svg')).not.toBeNull()
    expect(screen.getByLabelText('Work mode')).toHaveTextContent('remote')
    expect(screen.getByRole('heading', { name: 'Description' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Where it was found' })).toBeInTheDocument()
    const source = screen.getByRole('link', { name: /jobs\.example\.com\/1/ })
    expect(source.querySelector('svg')).not.toBeNull()
    const page = screen.getByRole('link', { name: 'Open the full job page' })
    expect(page.querySelector('svg')).not.toBeNull()
  })

  it('the edit icon opens a card over a blurred page, with the date, Undo and the details', async () => {
    const user = userEvent.setup()
    stubApi((call) => {
      if (call.path === '/jobs/a') {
        return {
          ...applied('a', 'Newest', '2026-11-05'),
          description: 'd',
          canonical_url: null,
          injection_flags: [],
          decision_history: [],
          first_search_id: null,
          company_id: null,
          location_text: null,
        }
      }
      if (call.path === '/jobs/a/interview') {
        return {
          job_id: 'a',
          can_edit: true,
          can_add_round: true,
          contact: null,
          source: null,
          rounds: [],
          status: { state: 'applied', round: null },
          resume: { state: 'none', resume_file_id: null, name: null, added_on: null },
        }
      }
      if (call.path.startsWith('/jobs?'))
        return {
          items: [applied('a', 'Newest', '2026-11-05')],
          next_cursor: null,
        }
      return undefined
    })
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <PipelinePage />
        </MemoryRouter>
      </QueryClientProvider>,
    )

    await user.click(await screen.findByRole('button', { name: /^Edit / }))

    const card = await screen.findByRole('region', {
      name: 'Edit Newest (Python) - Pune',
    })
    // inline under its job, like the Companies list: no dialog, no blurred backdrop
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(screen.queryByTestId('modal-backdrop')).not.toBeInTheDocument()
    const jobRow = screen.getByRole('link', { name: /Newest/ }).closest('tr') as HTMLElement
    expect(jobRow.nextElementSibling).toContainElement(card)
    expect(await within(card).findByText('Applied on 5 Nov 2026')).toBeInTheDocument()
    expect(within(card).getByRole('button', { name: 'Undo' })).toBeInTheDocument()
    expect(await within(card).findByLabelText('Contact name')).toBeInTheDocument()

    // each part is an accent card with an icon heading, like Preferences and Search rules
    for (const name of ['Point of contact', 'How the job came', 'Interview rounds']) {
      const part = within(card).getByRole(name === 'Interview rounds' ? 'region' : 'form', { name })
      expect(part).toHaveClass('ht-detail-card')
      expect(within(part).getByRole('heading', { name })).toHaveClass('ht-detail-heading')
    }
    // the close cross turns red under the pointer
    expect(within(card).getByRole('button', { name: 'Close' })).toHaveClass('ht-close-button')

    await user.keyboard('{Escape}')

    expect(screen.queryByRole('region', { name: /^Edit / })).not.toBeInTheDocument()
  })

  it('shows_the_short_role_with_the_full_title_on_hover', async () => {
    renderPage()
    const link = await screen.findByRole('link', { name: 'Newest' })
    expect(link).toHaveAttribute('title', 'Newest (Python) - Pune')
  })

  it('shows_the_status_and_source_as_tags', async () => {
    renderPage()
    const table = await screen.findByRole('table', { name: 'Pipeline jobs' })
    const [, newest] = within(table).getAllByRole('row')
    if (!newest) throw new Error('expected a first row')
    expect(within(newest).getByText('Applied')).toHaveClass('ht-pill-green')
  })

  it('an inquired job shows an Inquired tag in its own colour', async () => {
    stubApi((call) =>
      call.path.startsWith('/jobs?')
        ? { items: [inquired('i', 'Asked', '2026-11-02')], next_cursor: null }
        : undefined,
    )
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <PipelinePage />
        </MemoryRouter>
      </QueryClientProvider>,
    )

    const tag = await screen.findByText('Inquired')

    expect(tag).toHaveClass('ht-pill-blue')
  })

  it('US1 AS3 the tab is in the address, and AS1 In pipeline is the default tab', async () => {
    stubApi((call) =>
      call.path.startsWith('/jobs?') ? { items: [], next_cursor: null } : undefined,
    )
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter initialEntries={['/']}>
          <PipelinePage />
        </MemoryRouter>
      </QueryClientProvider>,
    )

    const tabs = await screen.findByRole('navigation', { name: 'Home tabs' })

    expect(within(tabs).getByRole('link', { name: 'Explore' })).toHaveAttribute('href', '/explore')
    const pipeline = within(tabs).getByRole('link', { name: 'In pipeline' })
    expect(pipeline).toHaveAttribute('href', '/')
    expect(pipeline).toHaveAttribute('aria-current', 'page')
  })

  it('the tabs read In pipeline first, then Explore', async () => {
    renderPage()

    const tabs = await screen.findByRole('navigation', { name: 'Home tabs' })

    expect(
      within(tabs)
        .getAllByRole('link')
        .map((link) => link.textContent),
    ).toEqual(['In pipeline', 'Explore'])
  })

  it('US1 AS5 empty pipeline message', async () => {
    stubApi((call) =>
      call.path.startsWith('/jobs?') ? { items: [], next_cursor: null } : undefined,
    )
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <PipelinePage />
        </MemoryRouter>
      </QueryClientProvider>,
    )

    expect(
      await screen.findByText(
        'Nothing in your pipeline yet. Mark a job as applied or inquired in Explore.',
      ),
    ).toBeInTheDocument()
  })
})

describe('PipelinePage status column', () => {
  function renderWith(rows: unknown[]) {
    stubApi((call) =>
      call.path.startsWith('/jobs?') ? { items: rows, next_cursor: null } : undefined,
    )
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <PipelinePage />
        </MemoryRouter>
      </QueryClientProvider>,
    )
  }

  async function statusOf(title: string) {
    const link = await screen.findByRole('link', { name: title })
    const row = link.closest('tr')
    if (!row) throw new Error('no row')
    return within(row).getAllByRole('cell')[3]
  }

  it('US2 AS1 status reads Round 1 scheduled', async () => {
    renderWith([
      {
        ...applied('a', 'Backend', '2026-11-05'),
        interview: { state: 'scheduled', round: 1 },
      },
    ])

    expect(await statusOf('Backend')).toHaveTextContent('Round 1 scheduled')
  })

  it('shows the latest round cleared, and a failed round wins', async () => {
    renderWith([
      {
        ...applied('a', 'Cleared one', '2026-11-05'),
        interview: { state: 'cleared', round: 2 },
      },
      {
        ...applied('b', 'Failed one', '2026-11-04'),
        interview: { state: 'failed', round: 3 },
      },
    ])

    expect(await statusOf('Cleared one')).toHaveTextContent('Round 2 cleared')
    expect(await statusOf('Failed one')).toHaveTextContent('Failed in round 3')
  })

  it('without rounds the status stays Applied or Inquired', async () => {
    renderWith([
      { ...applied('a', 'Plain applied', '2026-11-05'), interview: null },
      inquired('b', 'Plain inquired', '2026-11-04'),
    ])

    expect(await statusOf('Plain applied')).toHaveTextContent('Applied')
    expect(await statusOf('Plain inquired')).toHaveTextContent('Inquired')
  })

  it('each status has its own colour and the words stay visible', async () => {
    renderWith([
      {
        ...applied('a', 'One', '2026-11-05'),
        interview: { state: 'scheduled', round: 1 },
      },
      {
        ...applied('b', 'Two', '2026-11-04'),
        interview: { state: 'cleared', round: 1 },
      },
      {
        ...applied('c', 'Three', '2026-11-03'),
        interview: { state: 'failed', round: 1 },
      },
    ])

    const tones = await Promise.all(
      ['One', 'Two', 'Three'].map(async (title) => {
        const pill = (await statusOf(title))?.querySelector('.ht-pill')
        return pill?.className
      }),
    )
    expect(new Set(tones).size).toBe(3)
  })
})

describe('PipelinePage unsaved edits', () => {
  const interview = {
    job_id: 'a',
    can_edit: true,
    can_add_round: true,
    contact: { name: 'Asha', role: null, email: null, phone: null, linkedin_url: null },
    source: null,
    rounds: [],
    status: { state: 'applied', round: null },
    resume: { state: 'none', resume_file_id: null, name: null, added_on: null },
  }

  function renderOpenable() {
    stubApi((call) => {
      if (call.path.startsWith('/jobs?')) {
        return {
          items: [applied('a', 'Backend', '2026-11-05')],
          next_cursor: null,
        }
      }
      if (call.path === '/jobs/a') {
        return {
          ...applied('a', 'Backend', '2026-11-05'),
          description: 'Build APIs.',
          sources: [],
        }
      }
      if (call.path === '/jobs/a/interview') return interview
      return undefined
    })
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <PipelinePage />
        </MemoryRouter>
      </QueryClientProvider>,
    )
  }

  it('an opened row only shows the details; changes are made from the edit card', async () => {
    const user = userEvent.setup()
    renderOpenable()
    await user.click(await screen.findByRole('button', { name: /Details for/ }))

    const name = await screen.findByLabelText('Contact name')
    expect(name.hasAttribute('readonly') || name.hasAttribute('disabled')).toBe(true)
    expect(screen.queryByRole('button', { name: /^(Save|Add)/ })).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /Details for/ }))
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Contact name')).not.toBeInTheDocument()
  })

  it('an opened row with nothing recorded says "Nothing yet." instead of empty fields', async () => {
    const user = userEvent.setup()
    stubApi((call) => {
      if (call.path.startsWith('/jobs?')) {
        return {
          items: [applied('a', 'Backend', '2026-11-05')],
          next_cursor: null,
        }
      }
      if (call.path === '/jobs/a') {
        return {
          ...applied('a', 'Backend', '2026-11-05'),
          description: 'd',
          sources: [],
        }
      }
      if (call.path === '/jobs/a/interview') {
        return { ...interview, contact: null, source: null, rounds: [] }
      }
      return undefined
    })
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <PipelinePage />
        </MemoryRouter>
      </QueryClientProvider>,
    )
    await user.click(await screen.findByRole('button', { name: /Details for/ }))

    expect(await screen.findByText('Nothing yet.')).toBeInTheDocument()
    expect(screen.queryByLabelText('Contact name')).not.toBeInTheDocument()
  })

  describe('the resume column (feature 002f)', () => {
    const chosen = {
      state: 'chosen',
      resume_file_id: 'f1',
      name: 'Backend_2025.pdf',
      added_on: '2026-10-02',
    }
    const none = { state: 'none', resume_file_id: null, name: null, added_on: null }
    const resumeCell = (row: HTMLElement) => within(row).getAllByRole('cell')[4] as HTMLElement

    async function rowsFor(...resumes: (unknown | undefined)[]) {
      const jobs = resumes.map((resume, i) => ({
        ...applied(`j${i}`, `Job ${i}`, '2026-11-05'),
        ...(resume === undefined ? {} : { resume }),
      }))
      renderPage(jobs)
      const table = await screen.findByRole('table', { name: 'Pipeline jobs' })
      return within(table).getAllByRole('row').slice(1)
    }

    it('US2 AS1 shows the name of the resume used', async () => {
      const [row] = await rowsFor(chosen)

      expect(resumeCell(row as HTMLElement)).toHaveTextContent('Backend_2025.pdf')
    })

    it('US2 AS2 shows a dash without a resume', async () => {
      const [withNone, withoutField] = await rowsFor(none, undefined)

      expect(resumeCell(withNone as HTMLElement)).toHaveTextContent('—')
      expect(resumeCell(withoutField as HTMLElement)).toHaveTextContent('—')
    })

    it('US2 AS4 shortens a long name and keeps the full name in a title', async () => {
      const long = `${'Backend_Engineer_Resume_'.repeat(6)}2025.pdf`
      const [row] = await rowsFor({ ...chosen, name: long })

      // the whole name is on the element's title; jsdom does no layout, so the cutting itself
      // is a styling matter that a browser run shows
      const name = within(resumeCell(row as HTMLElement)).getByText(long)
      expect(name).toHaveAttribute('title', long)
    })

    it('FR009 keeps the removed marker visible when a long name is cut short', async () => {
      const long = `${'Backend_Engineer_Resume_'.repeat(6)}2024.pdf`
      const [row] = await rowsFor({
        state: 'removed',
        resume_file_id: null,
        name: long,
        added_on: '2025-03-14',
      })

      const cell = resumeCell(row as HTMLElement)
      // the marker is its own element, apart from the name that can be cut short
      const marker = within(cell).getByText('(removed)')
      expect(marker).toBeInTheDocument()
      expect(marker).not.toContainElement(within(cell).getByText(long))
      expect(cell).toHaveTextContent(`${long} (removed)`)
    })

    it('FR009 shows a removed file as its name marked removed', async () => {
      const [row] = await rowsFor({
        state: 'removed',
        resume_file_id: null,
        name: 'Backend_2024.pdf',
        added_on: '2025-03-14',
      })

      expect(resumeCell(row as HTMLElement)).toHaveTextContent('Backend_2024.pdf (removed)')
    })
  })

  describe('the resume in the opened row (feature 002f)', () => {
    it('US2 AS3 shows the name and the day it was added', async () => {
      const user = userEvent.setup()
      const job = {
        ...applied('j0', 'Job 0', '2026-11-05'),
        resume: {
          state: 'chosen',
          resume_file_id: 'f1',
          name: 'Backend_2025.pdf',
          added_on: '2026-10-02',
        },
      }
      stubApi((call) => {
        if (call.path === '/jobs/j0')
          return { ...job, description: 'd', city: null, country: null, skills_found: [] }
        if (call.path === '/jobs/j0/interview')
          return {
            job_id: 'j0',
            can_edit: true,
            can_add_round: true,
            contact: null,
            source: null,
            rounds: [],
            status: { state: 'applied', round: null },
            resume: job.resume,
          }
        if (call.path.startsWith('/jobs?')) return { items: [job], next_cursor: null }
        return undefined
      })
      render(
        <QueryClientProvider
          client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
        >
          <MemoryRouter>
            <PipelinePage />
          </MemoryRouter>
        </QueryClientProvider>,
      )

      await user.click(await screen.findByRole('button', { name: /Details for/ }))

      expect(await screen.findByText('Backend_2025.pdf · added 2 Oct 2026')).toBeInTheDocument()
    })
  })
})

describe('the edit card resume guard (feature 002f)', () => {
  const file = {
    id: 'f1',
    kind: 'upload_pdf',
    original_name: 'Backend_2025.pdf',
    size_bytes: 1000,
    page_count: 1,
    parse_status: 'parsed',
    parse_result: null,
    created_at: '2026-10-02T09:00:00Z',
    has_open_review: false,
    open_review_id: null,
  }

  it('US3 AS3 closing the card with an unsaved resume change asks first', async () => {
    const user = userEvent.setup()
    stubApi((call) => {
      if (call.path === '/resumes') return [file]
      if (call.path === '/pipeline/resumes') return { last_choice: null, usage: [] }
      if (call.path === '/jobs/a')
        return {
          ...applied('a', 'Newest', '2026-11-05'),
          description: 'd',
          canonical_url: null,
          injection_flags: [],
          decision_history: [],
          first_search_id: null,
          company_id: null,
          location_text: null,
        }
      if (call.path === '/jobs/a/interview')
        return {
          job_id: 'a',
          can_edit: true,
          can_add_round: true,
          contact: null,
          source: null,
          rounds: [],
          status: { state: 'applied', round: null },
          resume: { state: 'none', resume_file_id: null, name: null, added_on: null },
        }
      if (call.path.startsWith('/jobs?'))
        return { items: [applied('a', 'Newest', '2026-11-05')], next_cursor: null }
      return undefined
    })
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <PipelinePage />
        </MemoryRouter>
      </QueryClientProvider>,
    )
    await user.click(await screen.findByRole('button', { name: /^Edit / }))
    const card = await screen.findByRole('region', { name: /^Edit / })
    await user.selectOptions(
      await within(card).findByRole('combobox', { name: 'Resume file' }),
      'f1',
    )

    await user.click(within(card).getByRole('button', { name: 'Close' }))

    expect(await screen.findByRole('alertdialog')).toBeInTheDocument()
  })

  it('after a refused save the form is clean, so closing the card does not ask', async () => {
    const user = userEvent.setup()
    const removed = {
      state: 'removed',
      resume_file_id: null,
      name: 'Backend_2025.pdf',
      added_on: '2026-10-02',
    }
    let refused = false
    stubApi((call) => {
      if (call.path === '/resumes') return [file]
      if (call.path === '/pipeline/resumes') return { last_choice: null, usage: [] }
      if (call.path === '/jobs/a/interview/resume') {
        refused = true
        return problem(422, 'Choose one of your stored resume files.', {
          errors: [{ field: 'resume_file_id', message: 'Choose one of your stored resume files.' }],
        })
      }
      if (call.path === '/jobs/a')
        return {
          ...applied('a', 'Newest', '2026-11-05'),
          description: 'd',
          canonical_url: null,
          injection_flags: [],
          decision_history: [],
          first_search_id: null,
          company_id: null,
          location_text: null,
        }
      if (call.path === '/jobs/a/interview')
        return {
          job_id: 'a',
          can_edit: true,
          can_add_round: true,
          contact: null,
          source: null,
          rounds: [],
          status: { state: 'applied', round: null },
          // the file was removed meanwhile: a read after the refusal shows the note
          resume: refused
            ? removed
            : { state: 'none', resume_file_id: null, name: null, added_on: null },
        }
      if (call.path.startsWith('/jobs?'))
        return { items: [applied('a', 'Newest', '2026-11-05')], next_cursor: null }
      return undefined
    })
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <PipelinePage />
        </MemoryRouter>
      </QueryClientProvider>,
    )
    await user.click(await screen.findByRole('button', { name: /^Edit / }))
    const card = await screen.findByRole('region', { name: /^Edit / })
    await user.selectOptions(
      await within(card).findByRole('combobox', { name: 'Resume file' }),
      'f1',
    )
    await user.click(within(card).getByRole('button', { name: 'Save resume' }))
    await within(card).findByText(/Backend_2025.pdf \(removed\)/)

    await user.click(within(card).getByRole('button', { name: 'Close' }))

    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()
    await waitFor(() =>
      expect(screen.queryByRole('region', { name: /^Edit / })).not.toBeInTheDocument(),
    )
  })
})
