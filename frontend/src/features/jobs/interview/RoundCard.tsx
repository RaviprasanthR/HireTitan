import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Field, inputClass } from '@/features/companies/Field'
import { errorOf } from './errors'
import { Message } from './FormMessage'
import {
  ROUND_KINDS,
  ROUND_STATES,
  useDeleteRound,
  useUpdateRound,
  type Round,
  type RoundKind,
  type RoundState,
} from './interviewApi'
import { CharCounter } from './CharCounter'
import { QuestionList } from './QuestionList'
import { roundStatus } from './roundStatus'
import { useReportUnsaved } from './unsaved'
import { fromLocalInput, toLocalInput } from './time'

type Form = {
  kind: RoundKind
  when: string
  interviewers: string
  state: RoundState
  feedback: string
}

const FEEDBACK_MAX = 10000

const formOf = (round: Round): Form => ({
  kind: round.kind,
  when: toLocalInput(round.scheduled_at),
  interviewers: round.interviewers ?? '',
  state: round.state,
  feedback: round.feedback ?? '',
})

/** One interview round: its type, date and time, interviewers and result (feature 002e, US2). */
export function RoundCard({
  jobId,
  round,
  editable,
}: {
  jobId: string
  round: Round
  editable: boolean
}) {
  const [form, setForm] = useState<Form>(() => formOf(round))
  const [dirty, setDirty] = useState(false)
  const update = useUpdateRound(jobId)
  // follow the server while the person has not typed: the round can change under the card
  const [seen, setSeen] = useState(() => JSON.stringify(formOf(round)))
  const incoming = JSON.stringify(formOf(round))
  if (incoming !== seen) {
    setSeen(incoming)
    if (!dirty && !update.isError) setForm(formOf(round))
  }
  const [confirming, setConfirming] = useState(false)
  const remove = useDeleteRound(jobId)
  const result = dirty ? null : update
  const error = errorOf(result?.error)
  const changed = JSON.stringify(form) !== JSON.stringify(formOf(round))
  useReportUnsaved(changed || update.isPending || update.isError)
  const status = roundStatus(round.state, round.number)
  const change = (patch: Partial<Form>) => {
    setForm({ ...form, ...patch })
    setDirty(true)
  }

  return (
    <div className="space-y-3 rounded-md border border-divider p-3">
      <form
        aria-label={`Round ${round.number}`}
        className="space-y-2"
        onSubmit={(event) => {
          event.preventDefault()
          if (update.isPending) return // Enter in a field submits even while the button is off
          setDirty(false)
          update.mutate({
            id: round.id,
            changes: {
              kind: form.kind,
              interviewers: form.interviewers,
              state: form.state,
              feedback: form.feedback,
              // only a date the person changed is sent, so saving never rewrites seconds or
              // moves a time that was not touched
              ...(form.when !== toLocalInput(round.scheduled_at)
                ? { scheduled_at: fromLocalInput(form.when) }
                : {}),
            },
          })
        }}
      >
        <div className="flex flex-wrap items-center gap-3">
          <h3 className="text-sm font-semibold">Round {round.number}</h3>
          <span className={`ht-pill ht-pill-${status.tone}`}>{status.label}</span>
          {!round.scheduled_at && <span className="text-sm text-muted-small">Date not set</span>}
        </div>
        <div className="grid gap-2 sm:grid-cols-2">
          <Field label="Type" error={error?.fieldError('kind')}>
            {(props) => (
              <select
                {...props}
                className={inputClass}
                value={form.kind}
                disabled={!editable || update.isPending}
                onChange={(e) => change({ kind: e.target.value as RoundKind })}
              >
                {ROUND_KINDS.map((kind) => (
                  <option key={kind.value} value={kind.value}>
                    {kind.label}
                  </option>
                ))}
              </select>
            )}
          </Field>
          <Field label="Result" error={error?.fieldError('state')}>
            {(props) => (
              <select
                {...props}
                className={inputClass}
                value={form.state}
                disabled={!editable || update.isPending}
                onChange={(e) => change({ state: e.target.value as RoundState })}
              >
                {ROUND_STATES.map((state) => (
                  <option key={state.value} value={state.value}>
                    {state.label}
                  </option>
                ))}
              </select>
            )}
          </Field>
          <Field label="Date and time" error={error?.fieldError('scheduled_at')}>
            {(props) => (
              <input
                {...props}
                type="datetime-local"
                className={inputClass}
                value={form.when}
                disabled={!editable || update.isPending}
                onChange={(e) => change({ when: e.target.value })}
              />
            )}
          </Field>
          <Field label="Interviewers" error={error?.fieldError('interviewers')}>
            {(props) => (
              <input
                {...props}
                className={inputClass}
                maxLength={300}
                value={form.interviewers}
                disabled={!editable || update.isPending}
                onChange={(e) => change({ interviewers: e.target.value })}
              />
            )}
          </Field>
        </div>
        <div className="space-y-1">
          <label htmlFor={`${round.id}-feedback`} className="text-sm font-medium">
            Feedback
          </label>
          <textarea
            id={`${round.id}-feedback`}
            className={inputClass}
            rows={3}
            maxLength={FEEDBACK_MAX}
            value={form.feedback}
            disabled={!editable || update.isPending}
            aria-invalid={error?.fieldError('feedback') ? true : undefined}
            onChange={(e) => change({ feedback: e.target.value })}
          />
          <CharCounter length={form.feedback.length} max={FEEDBACK_MAX} />
          {error?.fieldError('feedback') && (
            <p className="text-sm text-danger">{error.fieldError('feedback')}</p>
          )}
        </div>
        {editable && !confirming && (
          <div className="flex flex-wrap items-center gap-3">
            <Button type="submit" size="sm" disabled={update.isPending}>
              Save round {round.number}
            </Button>
            <Button type="button" variant="ghost" size="sm" onClick={() => setConfirming(true)}>
              Delete round {round.number}
            </Button>
            <Message
              error={result?.error}
              saved={result?.isSuccess ? 'Round saved.' : null}
              fields={['kind', 'state', 'scheduled_at', 'interviewers', 'feedback']}
            />
          </div>
        )}
        {confirming && (
          <div className="space-y-2">
            <p className="text-sm">
              Delete round {round.number} and its questions? The other rounds keep their numbers.
            </p>
            <div className="flex gap-2">
              <Button
                type="button"
                size="sm"
                disabled={remove.isPending}
                onClick={() => remove.mutate(round.id)}
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
      <QuestionList jobId={jobId} round={round} editable={editable} />
    </div>
  )
}
