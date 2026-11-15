import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ResumeFiles } from './ResumeFiles'

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

function file(id: string, name: string, extra: object = {}) {
  return {
    id,
    kind: 'upload_pdf',
    original_name: name,
    size_bytes: 2048,
    page_count: 2,
    parse_status: 'parsed',
    parse_result: null,
    created_at: '2026-11-04T09:00:00Z',
    has_open_review: false,
    open_review_id: null,
    ...extra,
  }
}

let calls: { method: string; url: string }[]
let files: ReturnType<typeof file>[]
let remove: () => Response

beforeEach(() => {
  calls = []
  files = [file('f1', 'cv-2025.pdf'), file('f2', 'cv-old.pdf', { has_open_review: true })]
  remove = () => new Response(null, { status: 204 })
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? 'GET'
      calls.push({ method, url })
      if (method === 'DELETE') {
        const response = remove()
        if (response.ok) files = files.filter((f) => !url.endsWith(f.id))
        return response
      }
      return json(files)
    }),
  )
})
afterEach(() => vi.unstubAllGlobals())

function renderList() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <ResumeFiles />
    </QueryClientProvider>,
  )
}

describe('ResumeFiles', () => {
  it('lists the stored resume files', async () => {
    renderList()
    expect(await screen.findByText('cv-2025.pdf')).toBeInTheDocument()
    expect(screen.getByText('cv-old.pdf')).toBeInTheDocument()
  })

  it('US4_AS1_confirm_then_delete', async () => {
    renderList()
    await screen.findByText('cv-2025.pdf')
    await userEvent.click(screen.getByRole('button', { name: 'Delete cv-2025.pdf' }))

    const dialog = screen.getByRole('alertdialog')
    expect(dialog).toHaveTextContent(/versions? you already confirmed keep/i)
    expect(calls.filter((c) => c.method === 'DELETE')).toEqual([])

    await userEvent.click(within(dialog).getByRole('button', { name: 'Delete file' }))

    await waitFor(() => expect(screen.queryByText('cv-2025.pdf')).not.toBeInTheDocument())
    expect(calls.filter((c) => c.method === 'DELETE')).toEqual([
      { method: 'DELETE', url: '/api/v1/resumes/f1' },
    ])
    expect(screen.getByText('cv-old.pdf')).toBeInTheDocument()
  })

  it('warns that an unsaved review goes with its file', async () => {
    renderList()
    await screen.findByText('cv-old.pdf')
    await userEvent.click(screen.getByRole('button', { name: 'Delete cv-old.pdf' }))
    expect(screen.getByRole('alertdialog')).toHaveTextContent(/unsaved review/i)
  })

  it('Cancel leaves the file alone', async () => {
    renderList()
    await screen.findByText('cv-2025.pdf')
    await userEvent.click(screen.getByRole('button', { name: 'Delete cv-2025.pdf' }))
    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    await waitFor(() => expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument())
    expect(calls.filter((c) => c.method === 'DELETE')).toEqual([])
  })

  it('shows the reason when the file cannot be deleted right now', async () => {
    remove = () =>
      new Response(
        JSON.stringify({ title: 'Conflict', detail: 'Your resume is being read right now. Try again in a moment.' }),
        { status: 409, headers: { 'Content-Type': 'application/problem+json' } },
      )
    renderList()
    await screen.findByText('cv-2025.pdf')
    await userEvent.click(screen.getByRole('button', { name: 'Delete cv-2025.pdf' }))
    await userEvent.click(screen.getByRole('button', { name: 'Delete file' }))
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent(/being read right now/))
    expect(screen.getByText('cv-2025.pdf')).toBeInTheDocument()
  })
})

describe('ResumeFiles removal and the jobs that use a file (feature 002f)', () => {
  type Call = { method: string; url: string }
  let log: Call[]
  let usage: { resume_file_id: string; jobs: number }[]
  let clearUses: () => Response

  beforeEach(() => {
    log = []
    usage = [{ resume_file_id: 'f1', jobs: 2 }]
    clearUses = () => new Response(null, { status: 204 })
    files = [file('f1', 'cv-2025.pdf'), file('f2', 'cv-old.pdf')]
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string, init?: RequestInit) => {
        const method = init?.method ?? 'GET'
        log.push({ method, url })
        if (url === '/api/v1/pipeline/resumes') return json({ last_choice: null, usage })
        if (method === 'DELETE' && url.endsWith('/uses')) return clearUses()
        if (method === 'DELETE') {
          files = files.filter((f) => !url.endsWith(f.id))
          return new Response(null, { status: 204 })
        }
        return json(files)
      }),
    )
  })

  const removals = () => log.filter((c) => c.method === 'DELETE').map((c) => c.url)

  async function openDialog(name: string) {
    renderList()
    await screen.findByText(name)
    // the use counts load alongside the list
    await waitFor(() => expect(log.some((c) => c.url === '/api/v1/pipeline/resumes')).toBe(true))
    await userEvent.click(screen.getByRole('button', { name: `Delete ${name}` }))
    return screen.getByRole('alertdialog')
  }

  it('US4 AS1 says how many jobs use the file and that the name stays as a note', async () => {
    const dialog = await openDialog('cv-2025.pdf')

    await waitFor(() => expect(dialog).toHaveTextContent('Used on 2 jobs.'))
    expect(dialog).toHaveTextContent(/name stays on them as a note/i)
  })

  it('US4 AS1 says "1 job" for one', async () => {
    usage = [{ resume_file_id: 'f1', jobs: 1 }]
    const dialog = await openDialog('cv-2025.pdf')

    await waitFor(() => expect(dialog).toHaveTextContent('Used on 1 job.'))
  })

  it('US4 says nothing extra for a file no job uses', async () => {
    const dialog = await openDialog('cv-old.pdf')

    expect(dialog).not.toHaveTextContent(/Used on/)
    expect(within(dialog).queryByRole('checkbox')).not.toBeInTheDocument()
  })

  it('US4 AS6 the option to also clear the name is off by default, and removing keeps the notes', async () => {
    const dialog = await openDialog('cv-2025.pdf')
    const option = await within(dialog).findByRole('checkbox', {
      name: 'Also clear the name from these jobs',
    })
    expect(option).not.toBeChecked()

    await userEvent.click(within(dialog).getByRole('button', { name: 'Delete file' }))

    await waitFor(() => expect(removals()).toEqual(['/api/v1/resumes/f1']))
  })

  it('US4 AS6 also clear the name clears the jobs first, then removes the file', async () => {
    const dialog = await openDialog('cv-2025.pdf')
    await userEvent.click(
      await within(dialog).findByRole('checkbox', { name: 'Also clear the name from these jobs' }),
    )

    await userEvent.click(within(dialog).getByRole('button', { name: 'Delete file' }))

    await waitFor(() =>
      expect(removals()).toEqual(['/api/v1/pipeline/resumes/f1/uses', '/api/v1/resumes/f1']),
    )
  })

  it('US4 AS6 a failed clear stops before the file is removed and says so', async () => {
    clearUses = () =>
      new Response(JSON.stringify({ title: 'Something went wrong', status: 500 }), {
        status: 500,
        headers: { 'Content-Type': 'application/problem+json' },
      })
    const dialog = await openDialog('cv-2025.pdf')
    await userEvent.click(
      await within(dialog).findByRole('checkbox', { name: 'Also clear the name from these jobs' }),
    )

    await userEvent.click(within(dialog).getByRole('button', { name: 'Delete file' }))

    expect(await within(dialog).findByRole('alert')).toBeInTheDocument()
    expect(removals()).toEqual(['/api/v1/pipeline/resumes/f1/uses']) // the file is still there
    expect(screen.getByText('cv-2025.pdf')).toBeInTheDocument()
  })

  it('refreshes the use counts and the jobs after a removal', async () => {
    const dialog = await openDialog('cv-2025.pdf')
    const before = log.filter((c) => c.url === '/api/v1/pipeline/resumes').length

    await userEvent.click(within(dialog).getByRole('button', { name: 'Delete file' }))

    await waitFor(() =>
      expect(log.filter((c) => c.url === '/api/v1/pipeline/resumes').length).toBeGreaterThan(before),
    )
  })

  it('the option is not remembered for the next file', async () => {
    usage = [
      { resume_file_id: 'f1', jobs: 2 },
      { resume_file_id: 'f2', jobs: 1 },
    ]
    const dialog = await openDialog('cv-2025.pdf')
    await userEvent.click(
      await within(dialog).findByRole('checkbox', { name: 'Also clear the name from these jobs' }),
    )
    await userEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }))

    await userEvent.click(screen.getByRole('button', { name: 'Delete cv-old.pdf' }))

    const again = await screen.findByRole('checkbox', { name: 'Also clear the name from these jobs' })
    expect(again).not.toBeChecked()
  })
})
