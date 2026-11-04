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
