import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { problem, stubApi, type Call } from '@/test/api'
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
    ...overrides,
  }
}

function renderPanel(handler: (call: Call) => unknown) {
  const calls = stubApi((call) => {
    if (call.method === 'GET' && call.path === '/jobs/a/interview') return handler(call)
    return handler(call)
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
    interviewers: null,
    feedback: null,
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
