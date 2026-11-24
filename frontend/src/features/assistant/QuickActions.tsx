import { Briefcase, ClipboardCheck, Link2, Loader2, Mail, MessageSquareText } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { useState } from 'react'
import { ApiError } from '@/api/client'
import { Button } from '@/components/ui/button'
import { useJobChoices, useQuickActions, type QuickAction } from './api'
import type { QuickStatus } from './changes'

const field =
  'w-full rounded-lg border border-white/10 bg-background px-2 py-1.5 text-sm outline-none focus-visible:ring-2 focus-visible:ring-primary/60'

const ICONS: Record<string, LucideIcon> = {
  linkedin_request: Link2,
  linkedin_message: MessageSquareText,
  email: Mail,
  update_status: ClipboardCheck,
  add_job: Briefcase,
}

const STATUSES: { value: QuickStatus; label: string }[] = [
  { value: 'applied', label: 'Applied' },
  { value: 'inquired', label: 'Inquired' },
  { value: 'not_applied', label: 'Not applied (take back)' },
  { value: 'not_inquired', label: 'Not inquired (take back)' },
]

function problemText(error: unknown): string {
  if (error instanceof ApiError) return error.detail
  return error instanceof Error ? error.message : 'That did not work.'
}

/**
 * The chat's first way in (FR-029, amended 2026-11-24): five quick actions, each with a small
 * form. They run HireTitan's own actions; nothing here calls the AI.
 */
export function QuickActions({
  disabled,
  onPick,
  onTypeInstead,
  typing,
}: {
  disabled: boolean
  onPick: (action: QuickAction) => void
  onTypeInstead: () => void
  typing: boolean
}) {
  const actions = useQuickActions()
  return (
    <div className="border-t border-white/[0.07] px-3 pb-3 pt-2" aria-label="Quick actions">
      <p className="mb-1.5 text-xs text-muted-small">What would you like to do?</p>
      <ul className="flex flex-wrap gap-1.5">
        {actions.data?.map((action, index) => {
          const Icon = ICONS[action.key] ?? Briefcase
          return (
            <li
              key={action.key}
              className="mikasa-rise"
              style={{ animationDelay: `${index * 40}ms` }}
            >
              <button
                type="button"
                disabled={disabled}
                onClick={() => onPick(action)}
                className="flex items-center gap-1.5 rounded-full border border-white/10 bg-background/60 px-3 py-1.5 text-xs transition-all hover:-translate-y-px hover:border-primary hover:bg-primary/15 disabled:pointer-events-none disabled:opacity-50"
              >
                <Icon aria-hidden className="size-3.5 text-[#a99ce6]" />
                {action.label}
              </button>
            </li>
          )
        })}
      </ul>
      {!typing && (
        <Button
          type="button"
          variant="link"
          size="xs"
          className="mt-1 h-auto px-0 text-sm text-link"
          disabled={disabled}
          onClick={onTypeInstead}
        >
          Ask something else
        </Button>
      )}
    </div>
  )
}

/** A job to act on, picked from the person's own jobs. */
function JobPick({ value, onChange }: { value: string; onChange: (job: string) => void }) {
  const jobs = useJobChoices(true)
  return (
    <label className="text-xs">
      Job
      <select
        className={field}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        disabled={jobs.isPending}
      >
        <option value="">{jobs.isPending ? 'Loading your jobs…' : 'Choose a job'}</option>
        {jobs.data?.map((job) => (
          <option key={job.id} value={`job:${job.id}`}>
            {job.title} at {job.company_name}
          </option>
        ))}
      </select>
    </label>
  )
}

function FormFrame({
  title,
  onBack,
  onSubmit,
  busy,
  problem,
  submit,
  disabled,
  children,
}: {
  title: string
  onBack: () => void
  onSubmit: () => void
  busy: boolean
  problem: string | null
  submit: string
  disabled: boolean
  children: React.ReactNode
}) {
  return (
    <form
      aria-label={title}
      className="mikasa-rise flex flex-col gap-2 border-t border-white/[0.07] p-3 text-sm"
      onSubmit={(event) => {
        event.preventDefault()
        onSubmit()
      }}
    >
      <p className="font-medium">{title}</p>
      {children}
      {problem && (
        <p role="alert" className="text-xs text-danger">
          {problem}
        </p>
      )}
      <div className="flex gap-2">
        <Button type="submit" size="sm" disabled={busy || disabled}>
          {busy && <Loader2 aria-hidden className="animate-spin" />}
          {submit}
        </Button>
        <Button type="button" size="sm" variant="ghost" onClick={onBack}>
          Back
        </Button>
      </div>
    </form>
  )
}

/** Update a job's status: pick the job and the status; small and undoable, so it applies at once. */
export function StatusForm({
  onBack,
  onRun,
}: {
  onBack: () => void
  onRun: (job: string, status: QuickStatus) => Promise<void>
}) {
  const [job, setJob] = useState('')
  const [status, setStatus] = useState<QuickStatus>('applied')
  const [busy, setBusy] = useState(false)
  const [problem, setProblem] = useState<string | null>(null)
  return (
    <FormFrame
      title="Update a job's status"
      onBack={onBack}
      busy={busy}
      problem={problem}
      submit="Update"
      disabled={!job}
      onSubmit={() => {
        setBusy(true)
        setProblem(null)
        onRun(job, status)
          .then(onBack)
          .catch((error: unknown) => setProblem(problemText(error)))
          .finally(() => setBusy(false))
      }}
    >
      <JobPick value={job} onChange={setJob} />
      <label className="text-xs">
        Status
        <select
          className={field}
          value={status}
          onChange={(event) => setStatus(event.target.value as QuickStatus)}
        >
          {STATUSES.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </label>
    </FormFrame>
  )
}
