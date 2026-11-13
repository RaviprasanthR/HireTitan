import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { problem, stubApi } from '@/test/api'
import type { Round } from './interviewApi'
import { QuestionList } from './QuestionList'

function aQuestion(position: number, question: string, answer: string | null = null) {
  return { id: `q${position}`, position, question, answer }
}

function aRound(questions: Round['questions'] = []): Round {
  return {
    id: 'r1',
    number: 1,
    kind: 'technical',
    state: 'scheduled',
    scheduled_at: null,
    interviewers: null,
    feedback: null,
    questions,
  }
}

function aPanel(round: Round) {
  return {
    job_id: 'a',
    can_edit: true,
    can_add_round: true,
    contact: null,
    source: null,
    rounds: [round],
    status: { state: 'scheduled', round: 1 },
  }
}

function renderList(round: Round, editable = true) {
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <QuestionList jobId="a" round={round} editable={editable} />
    </QueryClientProvider>,
  )
}

afterEach(() => vi.unstubAllGlobals())

describe('QuestionList', () => {
  it('US3 AS1 a question without an answer is kept, in order', async () => {
    const user = userEvent.setup()
    const calls = stubApi(() => aPanel(aRound([aQuestion(1, 'Design a rate limiter')])))
    renderList(aRound())

    await user.type(screen.getByLabelText('New question'), 'Design a rate limiter')
    await user.click(screen.getByRole('button', { name: 'Add question' }))

    const post = calls.find((c) => c.method === 'POST')
    expect(post?.path).toBe('/interview/rounds/r1/questions')
    expect(post?.body).toMatchObject({ question: 'Design a rate limiter' })
    expect(screen.getByLabelText('New question')).toHaveValue('')
  })

  it('lists the saved questions in order with their answers', () => {
    renderList(aRound([aQuestion(1, 'First', 'Answer one'), aQuestion(2, 'Second')]))

    const [first, second, ...rest] = screen.getAllByRole('listitem')
    if (!first || !second) throw new Error('expected two questions')
    expect(rest).toHaveLength(0)
    expect(within(first).getByLabelText('Question 1')).toHaveValue('First')
    expect(within(first).getByLabelText('Answer 1')).toHaveValue('Answer one')
    expect(within(second).getByLabelText('Answer 2')).toHaveValue('')
  })

  it('edits one question and saves only it', async () => {
    const user = userEvent.setup()
    const calls = stubApi(() =>
      aPanel(aRound([aQuestion(1, 'First', 'Mine'), aQuestion(2, 'Second')])),
    )
    renderList(aRound([aQuestion(1, 'First'), aQuestion(2, 'Second')]))

    await user.type(screen.getByLabelText('Answer 1'), 'Mine')
    await user.click(screen.getByRole('button', { name: 'Save question 1' }))

    const patch = calls.find((c) => c.method === 'PATCH')
    expect(patch?.path).toBe('/interview/questions/q1')
    expect(patch?.body).toEqual({ question: 'First', answer: 'Mine' })
    expect(await screen.findByText('Question saved.')).toBeInTheDocument()
  })

  it('US3 AS2 delete one leaves the rest', async () => {
    const user = userEvent.setup()
    const calls = stubApi(() => aPanel(aRound([aQuestion(2, 'Second')])))
    renderList(aRound([aQuestion(1, 'First'), aQuestion(2, 'Second')]))

    await user.click(screen.getByRole('button', { name: 'Delete question 1' }))

    const del = calls.find((c) => c.method === 'DELETE')
    expect(del?.path).toBe('/interview/questions/q1')
    expect(calls.filter((c) => c.method === 'DELETE')).toHaveLength(1)
  })

  it('US3 AS4 line breaks shown', () => {
    renderList(aRound([aQuestion(1, 'Line one\nLine two', 'a\n\nb')]))

    expect(screen.getByLabelText('Question 1')).toHaveValue('Line one\nLine two')
    expect(screen.getByLabelText('Answer 1')).toHaveValue('a\n\nb')
  })

  it('FR014 counter near the limit', async () => {
    const user = userEvent.setup()
    renderList(aRound())
    const box = screen.getByLabelText('New question')

    expect(screen.queryByText(/\/ 2,000/)).not.toBeInTheDocument()

    await user.click(box)
    await user.paste('q'.repeat(1900))

    expect(screen.getByText('1,900 / 2,000')).toBeInTheDocument()
    expect(box).toHaveAttribute('maxlength', '2000')
  })

  it('a question needs text before it can be added', () => {
    renderList(aRound())

    expect(screen.getByRole('button', { name: 'Add question' })).toBeDisabled()
  })

  it('shows a field error on its field', async () => {
    const user = userEvent.setup()
    stubApi(() =>
      problem(422, 'Unprocessable Entity', {
        errors: [{ field: 'answer', message: 'The answer can be at most 10000 characters.' }],
      }),
    )
    renderList(aRound([aQuestion(1, 'First')]))

    await user.type(screen.getByLabelText('Answer 1'), 'x')
    await user.click(screen.getByRole('button', { name: 'Save question 1' }))

    expect(
      await screen.findByText('The answer can be at most 10000 characters.'),
    ).toBeInTheDocument()
  })

  it('is read-only when the job left the pipeline', () => {
    renderList(aRound([aQuestion(1, 'First', 'Ans')]), false)

    expect(screen.getByLabelText('Question 1')).toBeDisabled()
    expect(
      screen.queryByRole('button', { name: /Save question|Delete question|Add question/ }),
    ).not.toBeInTheDocument()
    expect(screen.queryByLabelText('New question')).not.toBeInTheDocument()
  })
})
