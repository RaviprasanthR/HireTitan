import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { problem, stubApi } from '@/test/api'
import type { Interview } from './interviewApi'
import { RoundCard } from './RoundCard'
import { toLocalInput } from './time'

type Round = Interview['rounds'][number]

function aRound(overrides: Partial<Round> = {}): Round {
  return {
    id: 'r1',
    number: 1,
    kind: 'technical',
    state: 'scheduled',
    scheduled_at: null,
    interviewers: null,
    feedback: null,
    questions: [],
    ...overrides,
  }
}

function aPanel(rounds: Round[]) {
  return {
    job_id: 'a',
    can_edit: true,
    can_add_round: true,
    contact: null,
    source: null,
    rounds,
    status: { state: 'applied', round: null },
  }
}

function renderCard(round: Round, editable = true) {
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <RoundCard jobId="a" round={round} editable={editable} />
    </QueryClientProvider>,
  )
}

afterEach(() => vi.unstubAllGlobals())

describe('RoundCard', () => {
  it('US2 AS8 time shown in local time', () => {
    renderCard(aRound({ scheduled_at: '2026-11-14T10:30:00Z' }))

    const local = toLocalInput('2026-11-14T10:30:00Z')
    expect(local).toMatch(/^2026-11-1[45]T\d\d:\d\d$/)
    expect(screen.getByLabelText('Date and time')).toHaveValue(local)
    expect(screen.queryByText('Date not set')).not.toBeInTheDocument()
  })

  it('says so when the date is not set', () => {
    renderCard(aRound())

    expect(screen.getByLabelText('Date and time')).toHaveValue('')
    expect(screen.getByText('Date not set')).toBeInTheDocument()
  })

  it('shows the round number, type and state', () => {
    renderCard(aRound({ number: 2, kind: 'hr', state: 'cleared', interviewers: 'Asha' }))

    expect(screen.getByRole('heading', { name: /Round 2/ })).toBeInTheDocument()
    expect(screen.getByLabelText('Type')).toHaveValue('hr')
    expect(screen.getByLabelText('Result')).toHaveValue('cleared')
    expect(screen.getByLabelText('Interviewers')).toHaveValue('Asha')
  })

  it('saves the changed fields', async () => {
    const user = userEvent.setup()
    const calls = stubApi((call) => {
      if (call.method === 'PATCH' && call.path === '/interview/rounds/r1') {
        return aPanel([aRound({ kind: 'hr', state: 'cleared', interviewers: 'Asha' })])
      }
      return undefined
    })
    renderCard(aRound())

    await user.selectOptions(screen.getByLabelText('Type'), 'hr')
    await user.selectOptions(screen.getByLabelText('Result'), 'cleared')
    await user.type(screen.getByLabelText('Interviewers'), '  Asha  ')
    await user.click(screen.getByRole('button', { name: 'Save round 1' }))

    expect(await screen.findByText('Round saved.')).toBeInTheDocument()
    const patch = calls.find((c) => c.method === 'PATCH')
    expect(patch?.body).toMatchObject({ kind: 'hr', state: 'cleared', interviewers: '  Asha  ' })
    expect(patch?.body).not.toHaveProperty('scheduled_at') // the date was not touched
  })

  it('US3 AS3 a feedback note is saved with the round', async () => {
    const user = userEvent.setup()
    const calls = stubApi(() => aPanel([aRound({ feedback: 'Good on design.' })]))
    renderCard(aRound())

    await user.type(screen.getByLabelText('Feedback'), 'Good on design.')
    await user.click(screen.getByRole('button', { name: 'Save round 1' }))

    await screen.findByText('Round saved.')
    expect(calls.find((c) => c.method === 'PATCH')?.body).toMatchObject({
      feedback: 'Good on design.',
    })
  })

  it('sends a typed date and time as an instant', async () => {
    const user = userEvent.setup()
    const calls = stubApi(() => aPanel([aRound()]))
    renderCard(aRound())

    await user.type(screen.getByLabelText('Date and time'), '2026-11-14T10:30')
    await user.click(screen.getByRole('button', { name: 'Save round 1' }))

    await screen.findByText('Round saved.')
    const patch = calls.find((c) => c.method === 'PATCH')
    expect(patch?.body).toMatchObject({
      scheduled_at: new Date('2026-11-14T10:30').toISOString(),
    })
  })

  it('a field error shows on its field', async () => {
    const user = userEvent.setup()
    stubApi(() =>
      problem(422, 'Unprocessable Entity', {
        errors: [
          { field: 'interviewers', message: 'The interviewers can be at most 300 characters.' },
        ],
      }),
    )
    renderCard(aRound())

    await user.type(screen.getByLabelText('Interviewers'), 'Ben')
    await user.click(screen.getByRole('button', { name: 'Save round 1' }))

    expect(
      await screen.findByText('The interviewers can be at most 300 characters.'),
    ).toBeInTheDocument()
    expect(screen.getByLabelText('Interviewers')).toHaveAttribute('aria-invalid', 'true')
  })

  it('US2 AS6 deleting a round asks first', async () => {
    const user = userEvent.setup()
    const calls = stubApi((call) => (call.method === 'DELETE' ? aPanel([]) : undefined))
    renderCard(aRound({ number: 2 }))

    await user.click(screen.getByRole('button', { name: 'Delete round 2' }))

    expect(screen.getByText(/Delete round 2 and its questions/)).toBeInTheDocument()
    expect(calls.filter((c) => c.method === 'DELETE')).toHaveLength(0)

    await user.click(screen.getByRole('button', { name: 'Yes, delete' }))

    expect(calls.find((c) => c.method === 'DELETE')?.path).toBe('/interview/rounds/r1')
  })

  it('keeping the round after the question sends nothing', async () => {
    const user = userEvent.setup()
    const calls = stubApi(() => aPanel([]))
    renderCard(aRound())

    await user.click(screen.getByRole('button', { name: 'Delete round 1' }))
    await user.click(screen.getByRole('button', { name: 'Keep it' }))

    expect(calls).toHaveLength(0)
    expect(screen.getByRole('button', { name: 'Delete round 1' })).toBeInTheDocument()
  })

  it('is read-only when the job left the pipeline', () => {
    renderCard(aRound(), false)

    expect(screen.getByLabelText('Type')).toBeDisabled()
    expect(screen.getByLabelText('Interviewers')).toBeDisabled()
    expect(screen.queryByRole('button', { name: /Save round/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Delete round/ })).not.toBeInTheDocument()
  })
})
