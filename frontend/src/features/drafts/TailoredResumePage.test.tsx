import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, RouterProvider, createMemoryRouter } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { type Call, problem, stubApi } from '@/test/api'
import { TailoredResumePage } from './TailoredResumePage'
import { TailoredResumesList } from './TailoredResumesList'

const DOC = {
  contact: {
    name: 'Sam Rivera',
    email: 'sam@example.invalid',
    phone: null,
    location: 'Springfield',
  },
  headline: 'Backend engineer',
  summary: 'Backend engineer who builds reliable APIs.',
  experience: [
    {
      id: 'e1',
      employer: 'Northwind Labs',
      title: 'Backend Engineer',
      dates: 'Mar 2021 - Present',
      location: null,
      bullets: ['Built a Python service', 'Moved a PostgreSQL schema'],
    },
  ],
  skills: ['Python', 'PostgreSQL'],
  projects: [],
  education: [
    {
      id: 'u1',
      institution: 'Lakeside University',
      detail: 'BSc',
      dates: '2015 - 2019',
    },
  ],
  certifications: [],
}

function tailored(over: Record<string, unknown> = {}) {
  return {
    id: 't1',
    status: 'ready',
    paused_reason: null,
    document: DOC,
    keyword_match: {
      matched: ['Python'],
      missing: [
        { keyword: 'Kubernetes', reason: 'not_in_profile' },
        { keyword: 'Terraform', reason: 'not_in_resume' },
      ],
      score: 0.5,
    },
    source: 'ai',
    edited: false,
    failure_reason: null,
    injection_signals: [],
    updated_at: '2026-11-17T09:00:00Z',
    ...over,
  }
}

type Setup = { resume?: unknown; start?: unknown }

function renderPage({ resume, start }: Setup = {}) {
  const calls = stubApi((call: Call) => {
    if (call.path === '/jobs/j1')
      return {
        id: 'j1',
        title: 'Backend Engineer',
        company_name: 'Acme',
        state: 'explore',
        sources: [],
        decision_history: [],
        injection_flags: [],
        description: 'text',
        company_id: null,
      }
    if (call.path === '/jobs/j1/tailored-resume' && call.method === 'GET')
      return resume ?? problem(404, 'Not Found', { reason: 'not_tailored' })
    if (call.path === '/jobs/j1/tailored-resume' && call.method === 'POST')
      return start ?? { job_id: 'j1', status: 'writing' }
    if (call.path === '/jobs/j1/tailored-resume' && call.method === 'PUT')
      return tailored({ edited: true })
    if (call.path === '/jobs/j1/tailored-resume' && call.method === 'DELETE')
      return new Response(null, { status: 204 })
    if (call.path === '/jobs/j1/description' && call.method === 'PUT') return { id: 'j1' }
    return undefined
  })
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <RouterProvider
        router={createMemoryRouter(
          [
            { path: '/jobs/:id/resume', element: <TailoredResumePage /> },
            { path: '/jobs/:id', element: <p>The job page</p> },
          ],
          { initialEntries: ['/jobs/j1/resume'] },
        )}
      />
    </QueryClientProvider>,
  )
  return calls
}

afterEach(() => vi.unstubAllGlobals())

describe('TailoredResumePage', () => {
  it('US4 AS1 shows the preview after tailoring', async () => {
    renderPage({ resume: tailored() })

    expect(await screen.findByRole('article', { name: 'Resume preview' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Sam Rivera' })).toBeInTheDocument()
    expect(screen.getByDisplayValue('Built a Python service')).toBeInTheDocument()
    expect(screen.getByText(/Backend Engineer, Northwind Labs/)).toBeInTheDocument()
  })

  it('US4 AS1 asks for the tailoring when there is none yet and says it is writing', async () => {
    const calls = renderPage()

    await waitFor(() => expect(calls.some((c) => c.method === 'POST')).toBe(true))
    expect(calls.find((c) => c.method === 'POST')?.body).toEqual({
      regenerate: false,
    })
  })

  it('US4 AS1 shows Tailoring… while it is written, with the paused reason', async () => {
    renderPage({
      resume: tailored({
        status: 'writing',
        document: null,
        paused_reason: 'Out of credit.',
      }),
    })

    expect(await screen.findByRole('status')).toHaveTextContent('Tailoring…')
    expect(screen.getByText('Out of credit.')).toBeInTheDocument()
  })

  it('US4 AS3 edits saved and kept', async () => {
    const user = userEvent.setup()
    const calls = renderPage({ resume: tailored() })
    const bullet = await screen.findByLabelText('Northwind Labs bullet 1')
    expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled()

    await user.clear(bullet)
    await user.type(bullet, 'Wrote my own bullet')
    await user.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => expect(calls.find((c) => c.method === 'PUT')).toBeTruthy())
    const sent = calls.find((c) => c.method === 'PUT')?.body as {
      document: typeof DOC
    }
    expect(sent.document.experience[0]?.bullets[0]).toBe('Wrote my own bullet')
    expect(sent.document.contact.name).toBe('Sam Rivera')
  })

  it('US4 AS3 asks before leaving with unsaved edits', async () => {
    const user = userEvent.setup()
    renderPage({ resume: tailored() })
    await user.type(await screen.findByLabelText('Northwind Labs bullet 1'), ' more')

    await user.click(screen.getByRole('link', { name: 'Back to the job' }))

    expect(await screen.findByRole('alertdialog', { name: 'Unsaved changes' })).toBeInTheDocument()
  })

  it('US4 AS4 keyword match with missing reasons', async () => {
    renderPage({ resume: tailored() })

    const box = await screen.findByRole('region', { name: 'Keyword match' })
    expect(box).toHaveTextContent('Keyword match: 50%')
    expect(box).toHaveTextContent('Kubernetes: not in your profile')
    expect(box).toHaveTextContent('Terraform: in your profile but not in this resume')
  })

  it('US4 AS5 download links', async () => {
    renderPage({ resume: tailored() })

    const pdf = await screen.findByRole('link', { name: 'Download PDF' })
    const docx = screen.getByRole('link', { name: 'Download DOCX' })
    expect(pdf).toHaveAttribute('href', '/api/v1/jobs/j1/tailored-resume.pdf')
    expect(docx).toHaveAttribute('href', '/api/v1/jobs/j1/tailored-resume.docx')
  })

  it('US4 AS2 fallback says the rewording was not used', async () => {
    renderPage({ resume: tailored({ source: 'fallback' }) })

    expect(await screen.findByText(/rewording was not used/)).toBeInTheDocument()
  })

  it('US4 AS7 asks for a description', async () => {
    const user = userEvent.setup()
    const calls = renderPage({
      start: problem(409, 'Conflict', {
        detail: 'No description.',
        reason: 'no_description',
      }),
    })

    const box = await screen.findByLabelText('Job description')
    expect(screen.getByRole('button', { name: 'Save description' })).toBeDisabled()
    await user.click(box)
    await user.paste('We need a backend engineer. '.repeat(10))
    await user.click(screen.getByRole('button', { name: 'Save description' }))

    await waitFor(() =>
      expect(calls.some((c) => c.method === 'PUT' && c.path === '/jobs/j1/description')).toBe(true),
    )
    await waitFor(() => expect(calls.filter((c) => c.method === 'POST').length).toBe(2))
  })

  it('a start that failed can be tried again', async () => {
    const user = userEvent.setup()
    const calls = renderPage({
      start: problem(409, 'Conflict', { detail: 'No AI key is set up.', reason: 'ai_unavailable' }),
    })

    expect(await screen.findByRole('alert')).toHaveTextContent('No AI key is set up.')
    await user.click(screen.getByRole('button', { name: 'Try again' }))

    await waitFor(() => expect(calls.filter((c) => c.method === 'POST').length).toBe(2))
  })

  it('FR006 EC12 shows the injection notice', async () => {
    renderPage({
      resume: tailored({
        injection_signals: [{ rule_id: 'ai_instruction', severity: 'high', excerpt: 'x' }],
      }),
    })

    expect(await screen.findByRole('note')).toHaveTextContent('looks like instructions to an AI')
  })

  it('FR009 delete asks then removes', async () => {
    const user = userEvent.setup()
    const confirm = vi.spyOn(window, 'confirm').mockReturnValueOnce(false).mockReturnValue(true)
    const calls = renderPage({ resume: tailored() })
    await screen.findByRole('article', { name: 'Resume preview' })

    await user.click(screen.getByRole('button', { name: 'Delete' }))
    expect(calls.some((c) => c.method === 'DELETE')).toBe(false)
    await user.click(screen.getByRole('button', { name: 'Delete' }))

    await waitFor(() => expect(calls.some((c) => c.method === 'DELETE')).toBe(true))
    expect(await screen.findByText('The job page')).toBeInTheDocument()
    confirm.mockRestore()
  })
})

describe('TailoredResumesList', () => {
  it('US4 AS6 listed on the profile page', async () => {
    stubApi((call) =>
      call.path === '/tailored-resumes'
        ? [
            {
              job_id: 'j1',
              job_title: 'Backend Engineer',
              company: 'Acme',
              updated_at: '2026-11-17T09:00:00Z',
              source: 'ai',
              edited: false,
            },
          ]
        : undefined,
    )
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <TailoredResumesList />
        </MemoryRouter>
      </QueryClientProvider>,
    )

    expect(await screen.findByRole('heading', { name: 'Tailored resumes' })).toBeInTheDocument()
    expect(await screen.findByText('Backend Engineer, Acme')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Open' })).toHaveAttribute('href', '/jobs/j1/resume')
    expect(screen.getByRole('link', { name: 'PDF' })).toHaveAttribute(
      'href',
      '/api/v1/jobs/j1/tailored-resume.pdf',
    )
    expect(screen.getByRole('link', { name: 'DOCX' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Delete tailored resume/ })).toBeInTheDocument()
  })
})
