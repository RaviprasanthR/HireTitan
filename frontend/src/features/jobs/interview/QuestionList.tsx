import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { CharCounter } from './CharCounter'
import { errorOf } from './errors'
import { Message } from './FormMessage'
import { useReportUnsaved } from './unsaved'
import { useAddQuestion, useDeleteQuestion, useUpdateQuestion, type Round } from './interviewApi'

export const QUESTION_MAX = 2000
export const ANSWER_MAX = 10000

const areaClass =
  'w-full rounded-md border border-muted-foreground bg-background px-3 py-1.5 text-sm'

type Question = Round['questions'][number]

function QuestionItem({
  jobId,
  question,
  editable,
}: {
  jobId: string
  question: Question
  editable: boolean
}) {
  const [text, setText] = useState(question.question)
  const [answer, setAnswer] = useState(question.answer ?? '')
  const [dirty, setDirty] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const update = useUpdateQuestion(jobId)
  // follow the server while the person has not typed
  const incoming = JSON.stringify([question.question, question.answer])
  const [seen, setSeen] = useState(incoming)
  if (incoming !== seen) {
    setSeen(incoming)
    if (!dirty && !update.isError) {
      setText(question.question)
      setAnswer(question.answer ?? '')
    }
  }
  const remove = useDeleteQuestion(jobId)
  const result = dirty ? null : update
  const error = errorOf(result?.error)
  const n = question.position
  // unsaved means different from what is stored, so typing a letter and deleting it is not a
  // change; a save in flight or one that failed still counts (FR-013)
  const changed = text !== question.question || answer !== (question.answer ?? '')
  useReportUnsaved(changed || update.isPending || update.isError)

  return (
    <li>
      <form
        aria-label={`Edit question ${n}`}
        className="space-y-2"
        onSubmit={(event) => {
          event.preventDefault()
          if (update.isPending) return
          setDirty(false)
          update.mutate({ id: question.id, changes: { question: text, answer } })
        }}
      >
        <div className="space-y-1">
          <label htmlFor={`${question.id}-q`} className="text-sm font-medium">
            Question {n}
          </label>
          <textarea
            id={`${question.id}-q`}
            className={areaClass}
            rows={2}
            maxLength={QUESTION_MAX}
            value={text}
            disabled={!editable || update.isPending}
            aria-invalid={error?.fieldError('question') ? true : undefined}
            onChange={(e) => {
              setText(e.target.value)
              setDirty(true)
            }}
          />
          <CharCounter length={text.length} max={QUESTION_MAX} />
          {error?.fieldError('question') && (
            <p className="text-sm text-danger">{error.fieldError('question')}</p>
          )}
        </div>
        <div className="space-y-1">
          <label htmlFor={`${question.id}-a`} className="text-sm font-medium">
            Answer {n}
          </label>
          <textarea
            id={`${question.id}-a`}
            className={areaClass}
            rows={3}
            maxLength={ANSWER_MAX}
            value={answer}
            disabled={!editable || update.isPending}
            aria-invalid={error?.fieldError('answer') ? true : undefined}
            onChange={(e) => {
              setAnswer(e.target.value)
              setDirty(true)
            }}
          />
          <CharCounter length={answer.length} max={ANSWER_MAX} />
          {error?.fieldError('answer') && (
            <p className="text-sm text-danger">{error.fieldError('answer')}</p>
          )}
        </div>
        {editable && !confirming && (
          <div className="flex flex-wrap items-center gap-3">
            <Button type="submit" size="sm" disabled={update.isPending || text.trim() === ''}>
              Save question {n}
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              disabled={remove.isPending}
              onClick={() => setConfirming(true)}
            >
              Delete question {n}
            </Button>
            <Message
              error={result?.error ?? remove.error}
              saved={result?.isSuccess ? 'Question saved.' : null}
              fields={['question', 'answer']}
            />
          </div>
        )}
        {confirming && (
          <div className="space-y-2">
            <p className="text-sm">Delete question {n} and its answer?</p>
            <div className="flex gap-2">
              <Button
                type="button"
                size="sm"
                disabled={remove.isPending}
                onClick={() => remove.mutate(question.id)}
              >
                Yes, delete
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => {
                  remove.reset()
                  setConfirming(false)
                }}
              >
                Keep it
              </Button>
            </div>
            {remove.isError && (
              <p role="alert" className="text-sm text-danger">
                {remove.error.message}
              </p>
            )}
          </div>
        )}
      </form>
    </li>
  )
}

/** The questions asked in one round and the answers given, in the order added (US3). */
export function QuestionList({
  jobId,
  round,
  editable,
}: {
  jobId: string
  round: Round
  editable: boolean
}) {
  const [text, setText] = useState('')
  const [answer, setAnswer] = useState('')
  const add = useAddQuestion(jobId)
  const error = errorOf(add.error)
  useReportUnsaved(text !== '' || answer !== '')

  return (
    <div className="space-y-2">
      <h4 className="text-sm font-semibold">Questions asked</h4>
      {round.questions.length === 0 && (
        <p className="text-sm text-muted-small">No questions recorded yet.</p>
      )}
      {round.questions.length > 0 && (
        <ol className="space-y-3">
          {round.questions.map((question) => (
            <QuestionItem key={question.id} jobId={jobId} question={question} editable={editable} />
          ))}
        </ol>
      )}
      {editable && (
        <form
          aria-label={`Add a question to round ${round.number}`}
          className="space-y-2"
          onSubmit={(event) => {
            event.preventDefault()
            if (add.isPending || text.trim() === '') return
            add.mutate(
              { roundId: round.id, question: text, ...(answer ? { answer } : {}) },
              {
                onSuccess: () => {
                  setText('')
                  setAnswer('')
                },
              },
            )
          }}
        >
          <div className="space-y-1">
            <label htmlFor={`${round.id}-new-q`} className="text-sm font-medium">
              New question
            </label>
            <textarea
              id={`${round.id}-new-q`}
              className={areaClass}
              rows={2}
              maxLength={QUESTION_MAX}
              value={text}
              disabled={add.isPending}
              onChange={(e) => setText(e.target.value)}
            />
            <CharCounter length={text.length} max={QUESTION_MAX} />
            {error?.fieldError('question') && (
              <p className="text-sm text-danger">{error.fieldError('question')}</p>
            )}
          </div>
          <div className="space-y-1">
            <label htmlFor={`${round.id}-new-a`} className="text-sm font-medium">
              Answer (optional)
            </label>
            <textarea
              id={`${round.id}-new-a`}
              className={areaClass}
              rows={2}
              maxLength={ANSWER_MAX}
              value={answer}
              disabled={add.isPending}
              onChange={(e) => setAnswer(e.target.value)}
            />
            <CharCounter length={answer.length} max={ANSWER_MAX} />
            {error?.fieldError('answer') && (
              <p className="text-sm text-danger">{error.fieldError('answer')}</p>
            )}
          </div>
          <div className="flex items-center gap-3">
            <Button type="submit" size="sm" disabled={add.isPending || text.trim() === ''}>
              Add question
            </Button>
            <Message error={add.error} saved={null} fields={['question', 'answer']} />
          </div>
        </form>
      )}
    </div>
  )
}
