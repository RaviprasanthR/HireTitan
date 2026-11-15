import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { json, problem, stubApi, type Call } from '@/test/api'
import { InterviewPanel } from './InterviewPanel'

function interview(overrides: Record<string, unknown> = {}) {
  return {
    job_id: 'a',
    can_edit: true,
    can_add_round: true,
    contact: null,
    source: null,
    rounds: [],
    status: { state: 'applied', round: null },
    resume: { state: 'none', resume_file_id: null, name: null, added_on: null },
    ...overrides,
  }
}

function renderPanel(handler: (call: Call) => unknown, readOnly = false) {
  const calls = stubApi((call) => {
    if (call.method === 'GET' && call.path === '/jobs/a/interview') return handler(call)
    return handler(call)
  })
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <InterviewPanel jobId="a" readOnly={readOnly} />
    </QueryClientProvider>,
  )
  return calls
}

describe('InterviewPanel contact and source', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('US1 AS1 shows the contact and the source sections', async () => {
    renderPanel(() => interview())

    expect(await screen.findByLabelText('Contact name')).toBeInTheDocument()
    expect(screen.getByLabelText('Role')).toBeInTheDocument()
    expect(screen.getByLabelText('Email')).toBeInTheDocument()
    expect(screen.getByLabelText('Phone')).toBeInTheDocument()
    expect(screen.getByLabelText('LinkedIn link')).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: 'Direct' })).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: 'Through a hiring firm' })).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: 'Not set' })).toBeChecked()
  })

  it('US1 AS2 contact with only a name saves', async () => {
    const user = userEvent.setup()
    const calls = renderPanel((call) => {
      if (call.method === 'PUT' && call.path === '/jobs/a/interview/contact') {
        return interview({
          contact: { name: 'Asha Rao', role: null, email: null, phone: null, linkedin_url: null },
        })
      }
      return interview()
    })
    await user.type(await screen.findByLabelText('Contact name'), 'Asha Rao')

    await user.click(screen.getByRole('button', { name: 'Save contact' }))

    expect(await screen.findByText('Contact saved.')).toBeInTheDocument()
    const put = calls.find((c) => c.method === 'PUT')
    expect(put?.path).toBe('/jobs/a/interview/contact')
    expect(put?.body).toMatchObject({ name: 'Asha Rao' })
  })

  it('shows the saved contact in the fields', async () => {
    renderPanel(() =>
      interview({
        contact: {
          name: 'Asha Rao',
          role: 'Recruiter',
          email: 'asha@example.com',
          phone: null,
          linkedin_url: 'https://linkedin.com/in/asha',
        },
      }),
    )

    expect(await screen.findByLabelText('Contact name')).toHaveValue('Asha Rao')
    expect(screen.getByLabelText('Role')).toHaveValue('Recruiter')
    expect(screen.getByLabelText('Email')).toHaveValue('asha@example.com')
    expect(screen.getByLabelText('LinkedIn link')).toHaveValue('https://linkedin.com/in/asha')
  })

  it('US1 AS3 a field error shows on that field and keeps what was typed', async () => {
    const user = userEvent.setup()
    renderPanel((call) => {
      if (call.method === 'PUT') {
        return problem(422, 'Unprocessable Entity', {
          errors: [{ field: 'email', message: 'That does not look like an email address.' }],
        })
      }
      return interview()
    })
    await user.type(await screen.findByLabelText('Contact name'), 'Asha')
    await user.type(screen.getByLabelText('Email'), 'not-an-email')

    await user.click(screen.getByRole('button', { name: 'Save contact' }))

    const email = screen.getByLabelText('Email')
    expect(await screen.findByText('That does not look like an email address.')).toBeInTheDocument()
    expect(email).toHaveAttribute('aria-invalid', 'true')
    expect(email).toHaveValue('not-an-email')
    expect(screen.getByLabelText('Contact name')).toHaveValue('Asha')
    expect(screen.queryByText('Contact saved.')).not.toBeInTheDocument()
  })

  it('US1 AS4 a hiring firm needs a name, and Direct hides the firm field', async () => {
    const user = userEvent.setup()
    const calls = renderPanel((call) => {
      if (call.method === 'PUT' && call.path === '/jobs/a/interview/source') {
        const body = call.body as { kind: string; firm_name?: string }
        if (body.kind === 'hiring_firm' && !body.firm_name) {
          return problem(422, 'Unprocessable Entity', {
            errors: [{ field: 'firm_name', message: 'A hiring firm needs a name.' }],
          })
        }
        return interview({ source: { kind: body.kind, firm_name: body.firm_name ?? null } })
      }
      return interview()
    })
    await user.click(await screen.findByRole('radio', { name: 'Through a hiring firm' }))
    expect(screen.getByLabelText('Firm name')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Save source' }))
    expect(await screen.findByText('A hiring firm needs a name.')).toBeInTheDocument()

    await user.type(screen.getByLabelText('Firm name'), 'TalentBridge')
    await user.click(screen.getByRole('button', { name: 'Save source' }))
    expect(await screen.findByText('Source saved.')).toBeInTheDocument()
    expect(calls.filter((c) => c.method === 'PUT').at(-1)?.body).toEqual({
      kind: 'hiring_firm',
      firm_name: 'TalentBridge',
    })

    await user.click(screen.getByRole('radio', { name: 'Direct' }))
    expect(screen.queryByLabelText('Firm name')).not.toBeInTheDocument()
  })

  it('review: after a save the fields show what the server kept (trimmed)', async () => {
    const user = userEvent.setup()
    renderPanel((call) => {
      if (call.method === 'PUT') {
        return interview({
          contact: { name: 'Asha', role: null, email: null, phone: null, linkedin_url: null },
        })
      }
      return interview()
    })
    await user.type(await screen.findByLabelText('Contact name'), 'Asha  ')

    await user.click(screen.getByRole('button', { name: 'Save contact' }))

    expect(await screen.findByText('Contact saved.')).toBeInTheDocument()
    expect(screen.getByLabelText('Contact name')).toHaveValue('Asha')
  })

  it('review: the saved message and a field error go away when the person edits again', async () => {
    const user = userEvent.setup()
    let fail = true
    renderPanel((call) => {
      if (call.method === 'PUT') {
        if (fail) {
          return problem(422, 'Unprocessable Entity', {
            errors: [{ field: 'email', message: 'That does not look like an email address.' }],
          })
        }
        return interview({
          contact: { name: 'Asha', role: null, email: null, phone: null, linkedin_url: null },
        })
      }
      return interview()
    })
    await user.type(await screen.findByLabelText('Contact name'), 'Asha')
    await user.type(screen.getByLabelText('Email'), 'x')
    await user.click(screen.getByRole('button', { name: 'Save contact' }))
    expect(await screen.findByText('That does not look like an email address.')).toBeVisible()

    await user.type(screen.getByLabelText('Email'), 'y')
    expect(screen.queryByText('That does not look like an email address.')).toBeNull()
    expect(screen.getByLabelText('Email')).not.toHaveAttribute('aria-invalid')

    fail = false
    await user.clear(screen.getByLabelText('Email'))
    await user.click(screen.getByRole('button', { name: 'Save contact' }))
    expect(await screen.findByText('Contact saved.')).toBeInTheDocument()
    await user.type(screen.getByLabelText('Role'), 'R')
    expect(screen.queryByText('Contact saved.')).toBeNull()
  })

  it('review: an error about a field the form does not show is still shown', async () => {
    const user = userEvent.setup()
    renderPanel((call) => {
      if (call.method === 'PUT') {
        return problem(422, 'Unprocessable Entity', {
          detail: 'A hiring firm needs a name.',
          errors: [{ field: 'firm_name', message: 'A hiring firm needs a name.' }],
        })
      }
      return interview()
    })
    await user.click(await screen.findByRole('radio', { name: 'Direct' }))

    await user.click(screen.getByRole('button', { name: 'Save source' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('A hiring firm needs a name.')
  })

  it('review: the fields are locked while the contact save is on its way', async () => {
    const user = userEvent.setup()
    let release: (response: Response) => void = () => undefined
    vi.stubGlobal(
      'fetch',
      vi.fn(async (_url: string, init?: RequestInit) => {
        if ((init?.method ?? 'GET') === 'PUT') {
          return new Promise<Response>((resolve) => {
            release = resolve
          })
        }
        return json(interview())
      }),
    )
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <InterviewPanel jobId="a" />
      </QueryClientProvider>,
    )
    await user.type(await screen.findByLabelText('Contact name'), 'Asha')

    await user.click(screen.getByRole('button', { name: 'Save contact' }))

    expect(screen.getByLabelText('Phone')).toBeDisabled()
    release(json(interview()))
  })

  it('review: a failed refresh keeps the forms and what was typed', async () => {
    const user = userEvent.setup()
    let failing = false
    stubApi(() => (failing ? problem(500, 'Down') : interview()))
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={client}>
        <InterviewPanel jobId="a" />
      </QueryClientProvider>,
    )
    await user.type(await screen.findByLabelText('Contact name'), 'Asha')

    failing = true
    await client.refetchQueries({ queryKey: ['job-interview'] })
    await waitFor(() =>
      expect(client.getQueryState(['job-interview', 'a'])?.status).toBe('error'),
    )
    await new Promise((resolve) => setTimeout(resolve, 20))

    expect(screen.getByLabelText('Contact name')).toHaveValue('Asha')
    expect(screen.queryByText('Could not load the details.')).not.toBeInTheDocument()
  })

  it('the panel is read-only when the job is not in the pipeline', async () => {
    renderPanel(() =>
      interview({
        can_edit: false,
        can_add_round: false,
        contact: { name: 'Asha Rao', role: null, email: null, phone: null, linkedin_url: null },
        status: { state: 'explore', round: null },
      }),
    )

    expect(await screen.findByLabelText('Contact name')).toBeDisabled()
    expect(screen.queryByRole('button', { name: 'Save contact' })).not.toBeInTheDocument()
    expect(screen.getByText(/not in your pipeline/i)).toBeInTheDocument()
  })

  it('FR015 shows no cost wording', async () => {
    renderPanel(() => interview())
    await screen.findByLabelText('Contact name')

    expect(document.body.textContent).not.toMatch(/AI cost|cost so far|budget|\bspend\b/i)
  })
})

function aRound(number: number, state: string, kind = 'technical') {
  return {
    id: `r${number}`,
    number,
    kind,
    state,
    scheduled_at: null,
    interviewers: null as string | null,
    feedback: null as string | null,
    questions: [],
  }
}

describe('InterviewPanel rounds', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('lists the rounds in order, each with its own card', async () => {
    renderPanel(() =>
      interview({
        rounds: [aRound(1, 'cleared'), aRound(2, 'scheduled', 'hr')],
        status: { state: 'scheduled', round: 2 },
      }),
    )

    expect(await screen.findByRole('heading', { name: /Round 1/ })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /Round 2/ })).toBeInTheDocument()
    expect(screen.getAllByLabelText('Type')).toHaveLength(2)
  })

  it('US2 AS1 Add round sends the chosen type and shows the new round', async () => {
    const user = userEvent.setup()
    let rounds: ReturnType<typeof aRound>[] = []
    const calls = renderPanel((call) => {
      if (call.method === 'POST' && call.path === '/jobs/a/interview/rounds') {
        rounds = [aRound(1, 'scheduled', 'hr')]
      }
      return interview({ rounds })
    })
    await user.selectOptions(await screen.findByLabelText('New round type'), 'hr')

    await user.click(screen.getByRole('button', { name: 'Add round' }))

    expect(await screen.findByRole('heading', { name: /Round 1/ })).toBeInTheDocument()
    const post = calls.find((c) => c.method === 'POST')
    expect(post?.body).toMatchObject({ kind: 'hr' })
  })

  it('US2 AS4 failed disables Add round with the reason', async () => {
    renderPanel(() =>
      interview({
        can_add_round: false,
        rounds: [aRound(1, 'failed')],
        status: { state: 'failed', round: 1 },
      }),
    )

    const add = await screen.findByRole('button', { name: 'Add round' })
    expect(add).toBeDisabled()
    expect(add).toHaveAccessibleDescription('A round failed, so no new round can be added.')
  })

  it('shows the error when a round cannot be added', async () => {
    const user = userEvent.setup()
    renderPanel((call) => {
      if (call.method === 'POST') {
        return problem(409, 'Conflict', {
          detail: 'A round failed, so no new round can be added. Change that round first.',
          reason: 'process_failed',
        })
      }
      return interview()
    })

    await user.click(await screen.findByRole('button', { name: 'Add round' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('A round failed')
  })

  it('a saved round shows what the server kept', async () => {
    const user = userEvent.setup()
    let rounds = [aRound(1, 'scheduled')]
    renderPanel((call) => {
      if (call.method === 'PATCH') rounds = [{ ...aRound(1, 'cleared'), interviewers: 'Asha' }]
      return interview({ rounds })
    })
    await user.selectOptions(await screen.findByLabelText('Result'), 'cleared')
    await user.type(screen.getByLabelText('Interviewers'), '  Asha  ')

    await user.click(screen.getByRole('button', { name: 'Save round 1' }))

    expect(await screen.findByText('Round saved.')).toBeInTheDocument()
    expect(screen.getByLabelText('Interviewers')).toHaveValue('Asha')
  })

  it('has no Add round button when the job is not in the pipeline', async () => {
    renderPanel(() =>
      interview({
        can_edit: false,
        can_add_round: false,
        rounds: [aRound(1, 'cleared')],
        status: { state: 'cleared', round: 1 },
      }),
    )

    expect(await screen.findByRole('heading', { name: /Round 1/ })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Add round' })).not.toBeInTheDocument()
  })
})

describe('InterviewPanel resume used (feature 002f)', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  const chosen = {
    state: 'chosen',
    resume_file_id: 'f1',
    name: 'Backend_2025.pdf',
    added_on: '2026-10-02',
  }

  it('US2 AS3 shows the resume name and the day it was added', async () => {
    renderPanel(() => interview({ resume: chosen }), true)

    expect(await screen.findByRole('heading', { name: 'Resume used' })).toBeInTheDocument()
    expect(screen.getByText('Backend_2025.pdf · added 2 Oct 2026')).toBeInTheDocument()
  })

  it('a job with only a resume is not shown as "Nothing yet."', async () => {
    renderPanel(() => interview({ resume: chosen }), true)

    await screen.findByText('Backend_2025.pdf · added 2 Oct 2026')
    expect(screen.queryByText('Nothing yet.')).not.toBeInTheDocument()
  })

  it('FR009 shows a removed file by its name, marked removed', async () => {
    renderPanel(
      () =>
        interview({
          resume: {
            state: 'removed',
            resume_file_id: null,
            name: 'Gone.pdf',
            added_on: '2025-03-14',
          },
        }),
      true,
    )

    expect(await screen.findByText('Gone.pdf (removed) · added 14 Mar 2025')).toBeInTheDocument()
  })

  it('a resume without a known day shows just its name', async () => {
    renderPanel(() => interview({ resume: { ...chosen, added_on: null } }), true)

    expect(await screen.findByText('Backend_2025.pdf')).toBeInTheDocument()
  })

  it('read-only with nothing recorded still says "Nothing yet."', async () => {
    renderPanel(() => interview(), true)

    expect(await screen.findByText('Nothing yet.')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Resume used' })).not.toBeInTheDocument()
  })

  it('an editable panel shows the section even with no resume', async () => {
    renderPanel(() => interview())

    expect(await screen.findByRole('heading', { name: 'Resume used' })).toBeInTheDocument()
    expect(screen.getByText('None')).toBeInTheDocument()
  })
})

describe('InterviewPanel resume editing (feature 002f)', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  const file = (id: string, name: string, at: string) => ({
    id,
    kind: 'upload_pdf',
    original_name: name,
    size_bytes: 1000,
    page_count: 1,
    parse_status: 'parsed',
    parse_result: null,
    created_at: at,
    has_open_review: false,
    open_review_id: null,
  })
  const FILES = [
    file('f1', 'Backend_2024.pdf', '2025-03-14T09:00:00Z'),
    file('f2', 'Backend_2025.pdf', '2026-10-02T09:00:00Z'),
  ]
  const chosen = (id: string, name: string, day: string) => ({
    state: 'chosen',
    resume_file_id: id,
    name,
    added_on: day,
  })
  const NONE = { state: 'none', resume_file_id: null, name: null, added_on: null }

  /** The panel over a job whose resume starts as `start`; writes change it as the server would. */
  function renderEditable(start: unknown, opts: { refuse?: boolean; afterRefusal?: unknown } = {}) {
    let current = start
    let refused = false
    const calls = stubApi((call) => {
      if (call.path === '/resumes') return FILES
      if (call.path === '/pipeline/resumes') return { last_choice: null, usage: [] }
      if (call.path === '/jobs/a/interview/resume') {
        if (call.method === 'PUT') {
          if (opts.refuse) {
            refused = true
            return problem(422, 'Choose one of your stored resume files.', {
              errors: [
                { field: 'resume_file_id', message: 'Choose one of your stored resume files.' },
              ],
            })
          }
          const id = (call.body as { resume_file_id: string }).resume_file_id
          const found = FILES.find((f) => f.id === id)
          current = chosen(id, found?.original_name ?? '', found?.created_at.slice(0, 10) ?? '')
        } else {
          current = NONE
        }
        return interview({ resume: current })
      }
      if (call.path === '/jobs/a/interview')
        return interview({ resume: refused && opts.afterRefusal ? opts.afterRefusal : current })
      return undefined
    })
    render(
      <QueryClientProvider
        client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
      >
        <InterviewPanel jobId="a" />
      </QueryClientProvider>,
    )
    return calls
  }
  const writes = (calls: { method: string; path: string; body?: unknown }[]) =>
    calls.filter((c) => c.path === '/jobs/a/interview/resume')

  it('US3 AS1 choose a resume and save', async () => {
    const user = userEvent.setup()
    const calls = renderEditable(NONE)
    const select = await screen.findByRole('combobox', { name: 'Resume file' })
    expect(screen.getByRole('button', { name: 'Save resume' })).toBeDisabled() // nothing changed

    await user.selectOptions(select, 'f2')
    await user.click(screen.getByRole('button', { name: 'Save resume' }))

    expect(await screen.findByText('Resume saved.')).toBeInTheDocument()
    expect(writes(calls)).toEqual([
      { method: 'PUT', path: '/jobs/a/interview/resume', body: { resume_file_id: 'f2' } },
    ])
    expect(
      screen.getByText('Backend_2025.pdf · added 2 Oct 2026', { selector: 'p' }),
    ).toBeInTheDocument()
  })

  it('US3 AS2 change the resume, then clear it', async () => {
    const user = userEvent.setup()
    const calls = renderEditable(chosen('f1', 'Backend_2024.pdf', '2025-03-14'))
    const select = await screen.findByRole('combobox', { name: 'Resume file' })
    expect(select).toHaveValue('f1')

    await user.selectOptions(select, 'f2')
    await user.click(screen.getByRole('button', { name: 'Save resume' }))
    expect(
      await screen.findByText('Backend_2025.pdf · added 2 Oct 2026', { selector: 'p' }),
    ).toBeInTheDocument()

    await user.selectOptions(screen.getByRole('combobox', { name: 'Resume file' }), 'None')
    await user.click(screen.getByRole('button', { name: 'Save resume' }))

    await waitFor(() => expect(writes(calls)).toHaveLength(2))
    expect(writes(calls).map((c) => c.method)).toEqual(['PUT', 'DELETE'])
    expect(await screen.findByRole('status')).toHaveTextContent('Resume saved.')
  })

  it('a removed file shows as a note with Clear, and Clear forgets it', async () => {
    const user = userEvent.setup()
    const calls = renderEditable({
      state: 'removed',
      resume_file_id: null,
      name: 'Gone.pdf',
      added_on: '2025-03-14',
    })

    expect(await screen.findByText('Gone.pdf (removed) · added 14 Mar 2025')).toBeInTheDocument()
    expect(await screen.findByRole('combobox', { name: 'Resume file' })).toHaveValue('') // None
    await user.click(screen.getByRole('button', { name: 'Clear' }))

    await waitFor(() => expect(writes(calls).map((c) => c.method)).toEqual(['DELETE']))
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Clear' })).not.toBeInTheDocument())
  })

  it('a file removed meanwhile is refused with a message and the note appears', async () => {
    const user = userEvent.setup()
    renderEditable(NONE, {
      refuse: true,
      afterRefusal: {
        state: 'removed',
        resume_file_id: null,
        name: 'Backend_2025.pdf',
        added_on: '2026-10-02',
      },
    })
    const select = await screen.findByRole('combobox', { name: 'Resume file' })

    await user.selectOptions(select, 'f2')
    await user.click(screen.getByRole('button', { name: 'Save resume' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Choose one of your stored')
    expect(screen.getByRole('button', { name: 'Save resume' })).toBeDisabled() // nothing pending
    expect(
      await screen.findByText('Backend_2025.pdf (removed) · added 2 Oct 2026'),
    ).toBeInTheDocument()
  })

  it('a second save that fails keeps the new pick instead of snapping back', async () => {
    const user = userEvent.setup()
    let failNext = false
    const stored = { current: chosen('f1', 'Backend_2024.pdf', '2025-03-14') as unknown }
    stubApi((call) => {
      if (call.path === '/resumes') return FILES
      if (call.path === '/pipeline/resumes') return { last_choice: null, usage: [] }
      if (call.path === '/jobs/a/interview/resume') {
        if (failNext) return problem(500, 'Something went wrong')
        stored.current = chosen('f2', 'Backend_2025.pdf', '2026-10-02')
        return interview({ resume: stored.current })
      }
      if (call.path === '/jobs/a/interview') return interview({ resume: stored.current })
      return undefined
    })
    render(
      <QueryClientProvider
        client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
      >
        <InterviewPanel jobId="a" />
      </QueryClientProvider>,
    )
    const select = await screen.findByRole('combobox', { name: 'Resume file' })
    await user.selectOptions(select, 'f2')
    await user.click(screen.getByRole('button', { name: 'Save resume' }))
    await screen.findByText('Resume saved.')

    failNext = true
    await user.selectOptions(screen.getByRole('combobox', { name: 'Resume file' }), 'None')
    await user.click(screen.getByRole('button', { name: 'Save resume' }))

    expect(await screen.findByRole('alert')).toBeInTheDocument()
    expect(screen.getByRole('combobox', { name: 'Resume file' })).toHaveValue('') // the pick stands
    expect(screen.getByRole('button', { name: 'Save resume' })).toBeEnabled()
  })

  it('a pick in progress survives a refresh that changes the stored resume', async () => {
    const user = userEvent.setup()
    const stored = { current: chosen('f1', 'Backend_2024.pdf', '2025-03-14') as unknown }
    stubApi((call) => {
      if (call.path === '/resumes') return FILES
      if (call.path === '/pipeline/resumes') return { last_choice: null, usage: [] }
      if (call.path === '/jobs/a/interview') return interview({ resume: stored.current })
      return undefined
    })
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={client}>
        <InterviewPanel jobId="a" />
      </QueryClientProvider>,
    )
    const select = await screen.findByRole('combobox', { name: 'Resume file' })
    await user.selectOptions(select, 'None')

    // the job is refreshed in the background and now shows its file as removed
    stored.current = {
      state: 'removed',
      resume_file_id: null,
      name: 'Backend_2024.pdf',
      added_on: '2025-03-14',
    }
    await act(() => client.invalidateQueries({ queryKey: ['job-interview', 'a'] }))

    expect(await screen.findByText(/Backend_2024.pdf \(removed\)/)).toBeInTheDocument()
    expect(screen.getByRole('combobox', { name: 'Resume file' })).toHaveValue('')
  })

  it('is not editable in the read-only view: no select and no Save', async () => {
    renderPanel(() => interview({ resume: chosen('f1', 'Backend_2024.pdf', '2025-03-14') }), true)

    await screen.findByText('Backend_2024.pdf · added 14 Mar 2025')
    expect(screen.queryByRole('combobox', { name: 'Resume file' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Save resume' })).not.toBeInTheDocument()
  })
})
