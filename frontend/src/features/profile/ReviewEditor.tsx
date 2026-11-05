import { zodResolver } from '@hookform/resolvers/zod'
import { useQuery } from '@tanstack/react-query'
import { Dialog } from 'radix-ui'
import { useEffect, useRef, useState } from 'react'
import { useForm } from 'react-hook-form'
import { useNavigate } from 'react-router'
import { ApiError, apiFetch } from '@/api/client'
import type { components } from '@/api/schema'
import { Button } from '@/components/ui/button'
import { fetchRun } from './api'
import { ProfileFormFields } from './ProfileFormFields'
import { type FormValues, formSchema, toApiContent, toFormPath, toFormValues } from './profileForm'

type Review = components['schemas']['ReviewOut']
type Dropped = { path: string; value: string; reason: string }
type HiddenRun = { page: number; text: string }
type Flag = { rule_id: string; severity: string; excerpt: string; location: string }
type Truncation = { offset: number; heading: string | null }

/** Where a dropped item can be put back, by what its path says it was. */
function restore(item: Dropped, form: ReturnType<typeof useForm<FormValues>>): boolean {
  const dirty = { shouldDirty: true }
  const path = item.path
  if (/^skills\[\d+\]$/.test(path)) {
    const skills = form.getValues('skills')
    form.setValue(
      'skills',
      skills
        ? `${skills}
${item.value}`
        : item.value,
      dirty,
    )
  } else if (path === 'summary') {
    form.setValue('summary', item.value, dirty)
  } else if (/^experience\[\d+\]$/.test(path)) {
    const [employer = '', title = ''] = item.value.split(' | ')
    const entry = { employer, title, location: '', start: '', end: '', current: false, bullets: '' }
    form.setValue('experience', [...form.getValues('experience'), entry], dirty)
  } else if (/^education\[\d+\]$/.test(path)) {
    const entry = {
      institution: item.value,
      qualification: '',
      field: '',
      start: '',
      end: '',
      grade: '',
    }
    form.setValue('education', [...form.getValues('education'), entry], dirty)
  } else if (/^projects\[\d+\]$/.test(path)) {
    const entry = { name: item.value, description: '', technologies: '', link: '' }
    form.setValue('projects', [...form.getValues('projects'), entry], dirty)
  } else if (/^certifications\[\d+\]$/.test(path)) {
    const entry = { name: item.value, issuer: '', date: '' }
    form.setValue('certifications', [...form.getValues('certifications'), entry], dirty)
  } else {
    return false
  }
  return true
}

const canRestore = (path: string) =>
  /^(skills\[\d+\]|summary|experience\[\d+\]|education\[\d+\]|projects\[\d+\]|certifications\[\d+\])$/.test(
    path,
  )

function FlagsPanel({ flags }: { flags: Record<string, unknown> }) {
  const hidden = (flags.hidden_text as HiddenRun[] | undefined) ?? []
  const injection = (flags.injection_flags as Flag[] | undefined) ?? []
  const truncated = (flags.truncated_at as Truncation | null | undefined) ?? null
  if (!hidden.length && !injection.length && !truncated) return null
  return (
    <section
      aria-label="Things we noticed in your file"
      className="space-y-3 rounded-lg border border-warning p-4"
    >
      <h2 className="font-semibold">Things we noticed in your file</h2>
      {hidden.length > 0 && (
        <div>
          <h3 className="font-medium">Hidden text found</h3>
          <p className="text-sm text-muted-small">
            This text is invisible when you open the file. It was left out and not used.
          </p>
          <ul className="list-disc pl-5 text-sm">
            {hidden.map((run, i) => (
              <li key={i}>
                Page {run.page}: {run.text}
              </li>
            ))}
          </ul>
        </div>
      )}
      {injection.length > 0 && (
        <div>
          <h3 className="font-medium">Text that looks like instructions to an AI</h3>
          <ul className="list-disc pl-5 text-sm">
            {injection.map((flag, i) => (
              <li key={i}>
                {flag.excerpt} <span className="text-muted-small">({flag.location})</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {truncated && (
        <p className="text-sm">
          Only the first {Number(truncated.offset ?? 0).toLocaleString('en-US')} characters were
          read
          {truncated.heading ? ` (the cut falls in "${truncated.heading}")` : ''}. Check that
          nothing important is missing below.
        </p>
      )}
    </section>
  )
}

type EmbeddedProps = {
  /** Inside a setup card: no page heading, and finishing hands control back to the card. */
  embedded?: boolean
  /** Pre-fills an empty contact name (the name given in setup step 1). */
  defaultName?: string
  /** Called instead of navigating when the review is confirmed or discarded. */
  onFinished?: () => void
}

function ReviewForm({
  review,
  debounceMs,
  embedded = false,
  defaultName,
  onFinished,
}: { review: Review; debounceMs: number } & EmbeddedProps) {
  const navigate = useNavigate()
  const finish = () => (onFinished ? onFinished() : navigate('/profile'))
  const initial = toFormValues(review.draft ?? review.extraction)
  if (defaultName && initial.contact.name.trim() === '') initial.contact.name = defaultName
  const form = useForm<FormValues>({
    resolver: zodResolver(formSchema),
    defaultValues: initial,
  })
  const [saveState, setSaveState] = useState<'idle' | 'saving' | 'saved' | 'error'>(
    review.draft_saved_at ? 'saved' : 'idle',
  )
  const [formError, setFormError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [confirmingDiscard, setConfirmingDiscard] = useState(false)
  const [restored, setRestored] = useState<Set<number>>(new Set())
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  const base = `/profile/reviews/${review.id}`
  const dropped = (review.dropped_items as unknown as Dropped[] | undefined) ?? []
  const latest = useRef(0) // numbers each save; only the newest one may change the indicator
  const queued = useRef<Promise<void>>(Promise.resolve()) // saves go out one at a time, in order
  const unsaved = useRef(false) // an edit is waiting for its debounce timer
  const locked = useRef(false) // set once Confirm starts: no more autosaves
  const mounted = useRef(true)

  useEffect(() => {
    mounted.current = true
    const saveDraft = () => {
      const seq = ++latest.current
      const json = toApiContent(form.getValues())
      queued.current = queued.current.then(() =>
        apiFetch(`${base}/draft`, { method: 'PUT', json }).then(
          () => {
            if (seq === latest.current && mounted.current) setSaveState('saved')
          },
          () => {
            if (seq === latest.current && mounted.current) setSaveState('error')
          },
        ),
      )
    }
    const subscription = form.watch(() => {
      if (locked.current) return
      clearTimeout(timer.current)
      unsaved.current = true
      setSaveState('saving')
      timer.current = setTimeout(() => {
        unsaved.current = false
        saveDraft()
      }, debounceMs)
    })
    return () => {
      mounted.current = false
      subscription.unsubscribe()
      clearTimeout(timer.current)
      if (unsaved.current && !locked.current) {
        unsaved.current = false
        saveDraft() // leaving the page must not lose the last edit
      }
    }
  }, [form, base, debounceMs])

  async function confirm(values: FormValues) {
    setFormError(null)
    setBusy(true)
    locked.current = true
    unsaved.current = false
    clearTimeout(timer.current)
    try {
      const { run_id } = await apiFetch<{ run_id: string }>(`${base}/confirm`, {
        method: 'POST',
        json: toApiContent(values),
      })
      let outcome: string | null = null
      for (let i = 0; i < 60 && mounted.current; i++) {
        try {
          const run = await fetchRun(run_id)
          if (['done', 'failed', 'cancelled'].includes(run.status)) {
            outcome = run.status
            break
          }
        } catch {
          break // the confirm was accepted; we just cannot see how it ended
        }
        await new Promise((resolve) => setTimeout(resolve, 500))
      }
      if (!mounted.current) return
      if (outcome === 'done') {
        finish()
        return
      }
      locked.current = false
      setFormError(
        outcome
          ? 'Your profile could not be saved. Your edits are kept here, so you can try Confirm again.'
          : 'We could not confirm that your profile was saved. Check the Profile page before trying again.',
      )
      setBusy(false)
    } catch (e) {
      if (e instanceof ApiError && e.status === 422) {
        for (const err of e.fieldErrors) {
          if (err.field === 'profile') setFormError(err.message)
          else {
            form.setError(
              toFormPath(err.field) as never,
              { type: 'server', message: err.message },
              { shouldFocus: true },
            )
          }
        }
        if (!e.fieldErrors.length) setFormError(e.detail)
      } else {
        setFormError(e instanceof ApiError ? e.detail : 'Something went wrong. Please try again.')
      }
      locked.current = false
      setBusy(false)
    }
  }

  async function discard() {
    setBusy(true)
    try {
      await apiFetch(`${base}/discard`, { method: 'POST' })
      finish()
    } catch (e) {
      setFormError(e instanceof ApiError ? e.detail : 'Could not discard this review.')
      setConfirmingDiscard(false)
      setBusy(false)
    }
  }

  return (
    <form onSubmit={form.handleSubmit(confirm)} className="max-w-3xl space-y-6" noValidate>
      <div className="flex items-start justify-between gap-4">
        {embedded ? (
          <div />
        ) : (
          <div>
            <h1 className="text-2xl font-semibold">Review your profile</h1>
            <p className="text-sm text-muted-small">
              Check what was found in your resume and correct anything. Nothing is saved as your
              profile until you confirm.
            </p>
          </div>
        )}
        <p aria-live="polite" className="text-sm text-muted-small">
          {saveState === 'saving' && 'Saving draft…'}
          {saveState === 'saved' && 'Draft saved'}
          {saveState === 'error' && 'Could not save the draft'}
        </p>
      </div>

      <FlagsPanel flags={review.flags} />

      {dropped.length > 0 && (
        <section
          aria-label="Not found in your resume"
          className="space-y-2 rounded-lg border border-muted-foreground p-4"
        >
          <h2 className="font-semibold">Not found in your resume</h2>
          <p className="text-sm text-muted-small">
            The AI suggested these, but they are not in your resume, so they were left out. Add one
            back if it is true.
          </p>
          <ul className="space-y-2">
            {dropped.map((item, i) =>
              restored.has(i) ? null : (
                <li key={i} className="flex flex-wrap items-center gap-3 text-sm">
                  <span className="font-medium">{item.value}</span>
                  <span className="text-muted-small">{item.reason}</span>
                  {canRestore(item.path) && (
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() => restore(item, form) && setRestored(new Set(restored).add(i))}
                    >
                      Add anyway
                    </Button>
                  )}
                </li>
              ),
            )}
          </ul>
        </section>
      )}

      <fieldset disabled={busy} className="m-0 min-w-0 border-0 p-0">
        <ProfileFormFields
          form={form}
          compare={review.compare_to}
          changedPaths={review.changed_paths}
        />
      </fieldset>

      {formError && (
        <p role="alert" className="rounded-md border border-danger p-3 text-danger">
          {formError}
        </p>
      )}

      <div className="flex flex-wrap items-center gap-3 border-t border-divider pt-4">
        <Button type="submit" variant="success" size="lg" disabled={busy}>
          Confirm profile
        </Button>
        <Button
          type="button"
          variant="danger"
          size="lg"
          disabled={busy}
          onClick={() => setConfirmingDiscard(true)}
        >
          {embedded ? 'Back to upload' : 'Discard'}
        </Button>
      </div>
      {review.provenance.provider !== 'none' && (
        <p className="text-xs text-muted-small">
          Extracted with {review.provenance.provider} · {review.provenance.model}
        </p>
      )}

      <Dialog.Root open={confirmingDiscard} onOpenChange={setConfirmingDiscard}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 bg-black/60" />
          <Dialog.Content className="fixed top-1/2 left-1/2 w-full max-w-md -translate-x-1/2 -translate-y-1/2 space-y-4 rounded-lg bg-surface p-6">
            <Dialog.Title className="text-lg font-semibold">
              {embedded
                ? 'Discard this profile and upload a different resume?'
                : 'Discard this review?'}
            </Dialog.Title>
            <Dialog.Description className="text-sm text-muted-small">
              Your edits are lost. Your current profile, if you have one, stays as it is.
            </Dialog.Description>
            <div className="flex gap-3">
              <Button type="button" variant="danger" onClick={() => void discard()} disabled={busy}>
                Yes, discard
              </Button>
              <Button type="button" variant="outline" onClick={() => setConfirmingDiscard(false)}>
                Keep editing
              </Button>
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </form>
  )
}

export function ReviewEditor({
  reviewId,
  debounceMs = 1000,
  ...embedded
}: { reviewId: string; debounceMs?: number } & EmbeddedProps) {
  const query = useQuery({
    queryKey: ['review', reviewId],
    queryFn: () => apiFetch<Review>(`/profile/reviews/${reviewId}`),
    refetchOnWindowFocus: false,
    staleTime: Infinity, // the form owns the data once loaded
  })
  if (query.isPending) return <p>Loading your review…</p>
  if (query.isError) {
    return (
      <p role="alert" className="text-danger">
        {query.error instanceof ApiError ? query.error.detail : 'Could not load this review.'}
      </p>
    )
  }
  return <ReviewForm review={query.data} debounceMs={debounceMs} {...embedded} />
}
