import { useEffect, useState } from 'react'
import { ApiError } from '@/api/client'
import { Button } from '@/components/ui/button'
import { useAddCompany, useDecideBoard, useDiscovery, type Company } from './api'
import { Field, inputClass } from './Field'

function Outcome({ text, onClose }: { text: string; onClose: () => void }) {
  return (
    <div className="space-y-3">
      <p>{text}</p>
      <Button type="button" size="sm" onClick={onClose}>
        Done
      </Button>
    </div>
  )
}

/** Step 2: the board found behind the careers link. Nothing is used until the person says so. */
function Suggestion({ company, onClose }: { company: Company; onClose: () => void }) {
  const discovery = useDiscovery(company.id)
  const decide = useDecideBoard(company.id)

  if (decide.isSuccess) {
    const board = decide.data.board_status === 'board'
    return (
      <Outcome
        onClose={onClose}
        text={
          board
            ? `${company.name} will be read through ${decide.data.ats_vendor}.`
            : `${company.name}’s careers page will be read.`
        }
      />
    )
  }
  if (discovery.isPending) return <p>Looking for a job board…</p>
  if (discovery.isError) {
    return (
      <div className="space-y-3">
        <p role="alert" className="text-sm text-danger">
          Could not look for a job board. {company.name} was added; you can try again later.
        </p>
        <Button type="button" size="sm" onClick={onClose}>
          Done
        </Button>
      </div>
    )
  }

  const { status, suggestion } = discovery.data
  const usable = status === 'found' && suggestion !== null
  let message = 'No job board found behind that link.'
  if (usable) {
    const jobs = suggestion.live_jobs
    message = `This looks like a ${suggestion.ats_vendor} board (${suggestion.board_id})${
      jobs === null ? '.' : ` with ${jobs} open jobs.`
    }`
  } else if (status === 'unsupported' && suggestion) {
    message = `This is a ${suggestion.ats_vendor} board, which HireTitan cannot read yet.`
  }

  return (
    <div className="space-y-3">
      <p>{message}</p>
      <div className="flex gap-2">
        {usable && (
          <Button
            type="button"
            size="sm"
            disabled={decide.isPending}
            onClick={() => decide.mutate('confirm')}
          >
            Yes, use this board
          </Button>
        )}
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={decide.isPending}
          onClick={() => decide.mutate('reject')}
        >
          {usable ? 'Not this one' : 'Read the careers page'}
        </Button>
      </div>
      {decide.isError && (
        <p role="alert" className="text-sm text-danger">
          {decide.error.message}
        </p>
      )}
    </div>
  )
}

/** Add a company by its careers link, then confirm the job board we suggest (FR-016, US3 AS2). */
export function AddCompanyDialog({ onClose }: { onClose: () => void }) {
  const [name, setName] = useState('')
  const [careersUrl, setCareersUrl] = useState('')
  const [city, setCity] = useState('')
  const [website, setWebsite] = useState('')
  const add = useAddCompany()
  const error = add.error instanceof ApiError ? add.error : null

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => event.key === 'Escape' && onClose()
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  // A square card over the page; the page behind it is blurred and a click on it closes the card.
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4 backdrop-blur-sm"
      onMouseDown={(event) => event.target === event.currentTarget && onClose()}
    >
      <section
        role="dialog"
        aria-modal="true"
        aria-label="Add a company"
        className="aspect-square w-[min(32rem,100%)] space-y-3 overflow-y-auto rounded-xl bg-surface p-6 shadow-[var(--ht-border-panel)]"
      >
        <h2 className="text-lg font-semibold">Add a company</h2>
        {add.isSuccess ? (
          <Suggestion company={add.data} onClose={onClose} />
        ) : (
          <form
            className="space-y-3"
            onSubmit={(event) => {
              event.preventDefault()
              add.mutate({
                name,
                careers_url: careersUrl,
                ...(city.trim() ? { city } : {}),
                ...(website.trim() ? { website } : {}),
              })
            }}
          >
            <Field label="Company name" error={error?.fieldError('name')}>
              {(props) => (
                <input
                  {...props}
                  className={inputClass}
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                />
              )}
            </Field>
            <Field label="Careers page link" error={error?.fieldError('careers_url')}>
              {(props) => (
                <input
                  {...props}
                  className={inputClass}
                  inputMode="url"
                  value={careersUrl}
                  onChange={(event) => setCareersUrl(event.target.value)}
                />
              )}
            </Field>
            <Field label="City (optional)" error={error?.fieldError('city')}>
              {(props) => (
                <input
                  {...props}
                  className={inputClass}
                  value={city}
                  onChange={(event) => setCity(event.target.value)}
                />
              )}
            </Field>
            <Field label="Website (optional)" error={error?.fieldError('website')}>
              {(props) => (
                <input
                  {...props}
                  className={inputClass}
                  inputMode="url"
                  value={website}
                  onChange={(event) => setWebsite(event.target.value)}
                />
              )}
            </Field>
            {add.isError && error?.fieldErrors.length === 0 && (
              <p role="alert" className="text-sm text-danger">
                {add.error.message}
              </p>
            )}
            <div className="flex gap-2">
              <Button type="submit" size="sm" disabled={add.isPending}>
                Find job board
              </Button>
              <Button type="button" variant="ghost" size="sm" onClick={onClose}>
                Cancel
              </Button>
            </div>
          </form>
        )}
      </section>
    </div>
  )
}
