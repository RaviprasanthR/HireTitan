import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { problem, stubApi } from '@/test/api'
import { PipelineControl } from './PipelineControl'

function file(id: string, name: string, createdAt: string, status = 'parsed') {
  return {
    id,
    kind: 'upload_pdf',
    original_name: name,
    size_bytes: 1000,
    page_count: 1,
    parse_status: status,
    parse_result: null,
    created_at: createdAt,
    has_open_review: false,
    open_review_id: null,
  }
}

const OLDER = file('f1', 'Backend_2024.pdf', '2025-03-14T09:00:00Z')
const NEWER = file('f2', 'Backend_2025.pdf', '2026-10-02T09:00:00Z')
const LETTER = file('f3', 'Letter.pdf', '2026-11-01T09:00:00Z', 'not_resume')

const JOB = { id: 'j1', title: 'Backend Engineer', state: 'applied' }

function renderControl(
  opts: {
    files?: unknown[]
    last?: string | null
    state?: string
    ownResumeId?: string | null
    lastFails?: boolean
    markFails?: boolean
  } = {},
) {
  const {
    files = [OLDER, NEWER, LETTER],
    last = null,
    state = 'explore',
    ownResumeId,
    lastFails = false,
    markFails = false,
  } = opts
  const calls = stubApi((call) => {
    if (call.path === '/resumes') return files
    if (call.path === '/pipeline/resumes')
      return lastFails ? problem(500, 'Something went wrong') : { last_choice: last, usage: [] }
    if (call.method === 'POST' && call.path.startsWith('/jobs/j1/'))
      return markFails ? problem(422, 'Choose one of your stored resume files.') : JOB
    return undefined
  })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <PipelineControl id="j1" state={state} ownResumeId={ownResumeId} />
    </QueryClientProvider>,
  )
  return Object.assign(calls, { client })
}

const marks = (calls: { method: string; path: string; body?: unknown }[]) =>
  calls.filter((c) => c.method === 'POST')

afterEach(() => vi.unstubAllGlobals())

describe('PipelineControl resume choice', () => {
  it('US1 AS4 starts on the last choice and sends it with the mark', async () => {
    const user = userEvent.setup()
    const calls = renderControl({ last: 'f2' })

    const select = await screen.findByRole('combobox', { name: 'Resume used' })
    expect(select).toHaveValue('f2')
    await user.click(screen.getByRole('button', { name: 'I applied' }))

    await waitFor(() => expect(marks(calls)).toHaveLength(1))
    expect(marks(calls)[0]).toMatchObject({
      path: '/jobs/j1/applied',
      body: { resume_file_id: 'f2' },
    })
  })

  it('US1 AS5 starts on None when the last choice is gone', async () => {
    renderControl({ last: 'f-removed' })

    expect(await screen.findByRole('combobox', { name: 'Resume used' })).toHaveValue('')
  })

  it('US1 AS3 one click still marks the job, recording None when nothing was picked', async () => {
    const user = userEvent.setup()
    const calls = renderControl({ last: null })
    await screen.findByRole('combobox', { name: 'Resume used' })

    await user.click(screen.getByRole('button', { name: 'I applied' }))

    await waitFor(() => expect(marks(calls)).toHaveLength(1))
    expect(marks(calls)[0]?.body).toEqual({ resume_file_id: null })
  })

  it('US1 AS6 sends no resume field and shows no choice without stored files', async () => {
    const user = userEvent.setup()
    const calls = renderControl({ files: [LETTER] }) // only a file rejected as not a resume

    await waitFor(() => expect(calls.some((c) => c.path === '/resumes')).toBe(true))
    await waitFor(() => expect(calls.some((c) => c.path === '/pipeline/resumes')).toBe(true))
    expect(screen.queryByRole('combobox', { name: 'Resume used' })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'I applied' }))

    await waitFor(() => expect(marks(calls)).toHaveLength(1))
    expect(marks(calls)[0]?.body).toBeUndefined()
  })

  it('a different choice is what the mark sends, together with a chosen date', async () => {
    const user = userEvent.setup()
    const calls = renderControl({ last: 'f2' })
    const select = await screen.findByRole('combobox', { name: 'Resume used' })
    await user.selectOptions(select, 'f1')
    await user.click(screen.getByRole('button', { name: 'Other date' }))
    const day = new Date()
    day.setDate(day.getDate() - 2)
    const iso = `${day.getFullYear()}-${String(day.getMonth() + 1).padStart(2, '0')}-${String(day.getDate()).padStart(2, '0')}`
    const date = screen.getByLabelText('Date')
    await user.clear(date)
    await user.type(date, iso)

    await user.click(screen.getByRole('button', { name: 'I inquired' }))

    await waitFor(() => expect(marks(calls)).toHaveLength(1))
    expect(marks(calls)[0]).toMatchObject({
      path: '/jobs/j1/inquired',
      body: { inquired_on: iso, resume_file_id: 'f1' },
    })
  })

  it('US1 AS2 an inquired job starts on its own resume, not on the last choice', async () => {
    const user = userEvent.setup()
    const calls = renderControl({ state: 'inquired', last: 'f2', ownResumeId: 'f1' })

    const select = await screen.findByRole('combobox', { name: 'Resume used' })
    expect(select).toHaveValue('f1')
    await user.click(screen.getByRole('button', { name: 'I applied' }))

    await waitFor(() => expect(marks(calls)).toHaveLength(1))
    expect(marks(calls)[0]).toMatchObject({
      path: '/jobs/j1/applied',
      body: { resume_file_id: 'f1' },
    })
  })

  it('FR012 offers a file that is still being read', async () => {
    renderControl({ files: [OLDER, file('f4', 'Fresh.pdf', '2026-11-05T09:00:00Z', 'pending')] })

    const select = await screen.findByRole('combobox', { name: 'Resume used' })
    expect(select).toHaveTextContent('Fresh.pdf')
  })

  it('FR003 an inquired job whose own resume is not known sends no resume and shows no choice', async () => {
    // the caller has not said which resume the job has, so one click must not overwrite it
    const user = userEvent.setup()
    const calls = renderControl({ state: 'inquired', last: 'f2' })

    await waitFor(() => expect(calls.some((c) => c.path === '/pipeline/resumes')).toBe(true))
    expect(screen.queryByRole('combobox', { name: 'Resume used' })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'I applied' }))

    await waitFor(() => expect(marks(calls)).toHaveLength(1))
    expect(marks(calls)[0]?.body).toBeUndefined()
  })

  it('FR003 an inquired job known to have no resume starts on the last choice', async () => {
    renderControl({ state: 'inquired', last: 'f2', ownResumeId: null })

    expect(await screen.findByRole('combobox', { name: 'Resume used' })).toHaveValue('f2')
  })

  it('FR001 choosing None sends null even when the choice started on a resume', async () => {
    const user = userEvent.setup()
    const calls = renderControl({ last: 'f2' })
    const select = await screen.findByRole('combobox', { name: 'Resume used' })

    await user.selectOptions(select, 'None')
    await user.click(screen.getByRole('button', { name: 'I applied' }))

    await waitFor(() => expect(marks(calls)).toHaveLength(1))
    expect(marks(calls)[0]?.body).toEqual({ resume_file_id: null })
  })

  it('a picked file that is removed meanwhile is not sent', async () => {
    const user = userEvent.setup()
    const calls = renderControl({ last: null })
    const select = await screen.findByRole('combobox', { name: 'Resume used' })
    await user.selectOptions(select, 'f1')

    // the file is removed on the Profile page; the shared list refreshes without it
    act(() => calls.client.setQueryData(['resumes'], [NEWER, LETTER]))
    await waitFor(() => expect(screen.getByRole('combobox', { name: 'Resume used' })).toHaveValue(''))
    await user.click(screen.getByRole('button', { name: 'I applied' }))

    await waitFor(() => expect(marks(calls)).toHaveLength(1))
    expect(marks(calls)[0]?.body).toEqual({ resume_file_id: null })
  })

  it('still offers the choice, starting on None, when the last choice cannot be read', async () => {
    renderControl({ lastFails: true })

    expect(await screen.findByRole('combobox', { name: 'Resume used' })).toHaveValue('')
  })

  it('shows the refusal of a mark, and clears it when the other mark succeeds', async () => {
    const user = userEvent.setup()
    renderControl({ markFails: true })
    await screen.findByRole('combobox', { name: 'Resume used' })

    await user.click(screen.getByRole('button', { name: 'I applied' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Choose one of your stored')
  })

  it('refreshes the last choice after a mark', async () => {
    const user = userEvent.setup()
    const calls = renderControl({ last: 'f2' })
    await screen.findByRole('combobox', { name: 'Resume used' })
    const before = calls.filter((c) => c.path === '/pipeline/resumes').length

    await user.click(screen.getByRole('button', { name: 'I applied' }))

    await waitFor(() =>
      expect(calls.filter((c) => c.path === '/pipeline/resumes').length).toBeGreaterThan(before),
    )
  })
})
