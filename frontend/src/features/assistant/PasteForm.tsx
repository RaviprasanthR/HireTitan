import { useState } from 'react'
import { ApiError } from '@/api/client'
import { Button } from '@/components/ui/button'
import type { PasteFields } from './changes'

const input = 'w-full rounded border border-divider bg-background px-2 py-1 text-sm'

/**
 * The composer's Paste a job description (FR-021): the text goes to the paste use case and is
 * never sent to the AI.
 */
export function PasteForm({
  initialDescription = '',
  onPaste,
  onDone,
  onClose,
}: {
  initialDescription?: string
  onPaste: (fields: PasteFields) => Promise<{ summary: string; refs?: string[] }>
  onDone?: (result: { summary: string; refs?: string[] }) => void
  onClose: () => void
}) {
  const [fields, setFields] = useState({
    url: '',
    title: '',
    company: '',
    description: initialDescription,
  })
  const [busy, setBusy] = useState(false)
  const [problem, setProblem] = useState<string | null>(null)
  const set = (key: keyof typeof fields) => (event: { target: { value: string } }) =>
    setFields((was) => ({ ...was, [key]: event.target.value }))
  return (
    <form
      aria-label="Paste a job description"
      className="flex flex-col gap-2 border-t border-divider p-3 text-sm"
      onSubmit={(event) => {
        event.preventDefault()
        setBusy(true)
        setProblem(null)
        onPaste({
          url: fields.url,
          description: fields.description,
          ...(fields.title.trim() ? { title: fields.title } : {}),
          ...(fields.company.trim() ? { company: fields.company } : {}),
        })
          .then((result) => {
            onDone?.(result)
            onClose()
          })
          .catch((error: unknown) => {
            const detail =
              error instanceof ApiError && error.problem.errors
                ? (error.problem.errors as { message: string }[]).map((e) => e.message).join(' ')
                : error instanceof Error
                  ? error.message
                  : 'The job could not be added.'
            setProblem(detail)
          })
          .finally(() => setBusy(false))
      }}
    >
      <p className="text-xs text-muted-small">
        The description is saved with the job and never sent to the AI.
      </p>
      <label className="text-xs">
        Link to the job
        <input className={input} value={fields.url} onChange={set('url')} />
      </label>
      <div className="flex gap-2">
        <label className="flex-1 text-xs">
          Job title (optional)
          <input className={input} value={fields.title} onChange={set('title')} />
        </label>
        <label className="flex-1 text-xs">
          Company (optional)
          <input className={input} value={fields.company} onChange={set('company')} />
        </label>
      </div>
      <label className="text-xs">
        Job description
        <textarea
          className={`${input} min-h-24`}
          value={fields.description}
          onChange={set('description')}
        />
      </label>
      {problem && (
        <p role="alert" className="text-xs text-danger">
          {problem}
        </p>
      )}
      <div className="flex gap-2">
        <Button type="submit" size="sm" disabled={busy}>
          Save job
        </Button>
        <Button type="button" size="sm" variant="ghost" onClick={onClose}>
          Cancel
        </Button>
      </div>
    </form>
  )
}
