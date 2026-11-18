import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { useSaveDescription } from '@/features/drafts/resumeApi'

const MIN = 200

/** Asks for the posting's text when a job has none, so a resume can be tailored to it. */
export function AddDescriptionDialog({
  jobId,
  onSaved,
  onCancel,
}: {
  jobId: string
  onSaved: () => void
  onCancel: () => void
}) {
  const [text, setText] = useState('')
  const save = useSaveDescription(jobId)
  const short = text.trim().length < MIN
  return (
    <form
      aria-label="Add the job description"
      className="space-y-2 rounded-lg bg-surface p-4"
      onSubmit={(event) => {
        event.preventDefault()
        save.mutate(text, { onSuccess: onSaved })
      }}
    >
      <p className="font-medium">Add the job description</p>
      <p className="text-sm text-muted-small">
        This job has no description yet. Paste the posting’s text so the resume can be tailored to
        it (at least {MIN} characters).
      </p>
      <textarea
        aria-label="Job description"
        className="w-full rounded-md border border-muted-foreground bg-background px-3 py-1.5 text-sm"
        rows={8}
        value={text}
        onChange={(event) => setText(event.target.value)}
      />
      {save.isError && (
        <p role="alert" className="text-sm text-danger">
          {save.error.message}
        </p>
      )}
      <div className="flex gap-2">
        <Button type="submit" size="sm" disabled={short || save.isPending}>
          Save description
        </Button>
        <Button type="button" variant="ghost" size="sm" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  )
}
