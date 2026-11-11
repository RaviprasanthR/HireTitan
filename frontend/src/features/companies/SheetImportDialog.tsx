import { useEffect, useRef, useState } from 'react'
import { ApiError } from '@/api/client'
import { Button } from '@/components/ui/button'
import { useSheetConfirm, useSheetPreview, type SheetPreview, type SheetResult } from './api'

const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`

function headersSeen(error: unknown): string[] {
  if (!(error instanceof ApiError)) return []
  const headers = (error.problem as { headers?: unknown }).headers
  return Array.isArray(headers) ? headers.filter((h): h is string => typeof h === 'string') : []
}

function resultText(result: SheetResult): string {
  return [
    `${plural(result.companies_added, 'company', 'companies')} added`,
    `${plural(result.contacts_added, 'contact')} added, ${result.contacts_updated} updated`,
    `${plural(result.notes_set, 'note')} set, ${result.notes_changed} changed, ${result.notes_kept} kept`,
    `${plural(result.skipped.length, 'row')} skipped`,
  ].join('. ')
}

function Issues({ label, items }: { label: string; items: SheetPreview['skipped'] }) {
  if (items.length === 0) return null
  return (
    <ul aria-label={label} className="list-disc pl-5 text-sm">
      {items.map((item) => (
        <li key={`${item.line}-${item.reason}`}>
          Row {item.line}: {item.reason}
        </li>
      ))}
    </ul>
  )
}

function Preview({
  plan,
  busy,
  error,
  onConfirm,
  onCancel,
}: {
  plan: SheetPreview
  busy: boolean
  error: string | null
  onConfirm: () => void
  onCancel: () => void
}) {
  const nothing =
    plan.companies.to_add +
      plan.contacts.to_add +
      plan.contacts.to_update +
      plan.notes.to_set +
      plan.notes.to_change ===
    0
  return (
    <section aria-label="Sheet preview" className="space-y-3 rounded-lg bg-surface p-4">
      <p className="text-sm">Columns used: {plan.columns.used.join(', ')}</p>
      {plan.columns.ignored.length > 0 && (
        <p className="text-sm text-muted-foreground">Ignored: {plan.columns.ignored.join(', ')}</p>
      )}
      <p className="font-medium">
        {plan.companies.matched} companies already on your list, {plan.companies.to_add} to add
      </p>
      <p>
        {plan.contacts.to_add} contacts to add, {plan.contacts.to_update} to update
      </p>
      <p>
        {plan.notes.to_set} notes to set, {plan.notes.to_change} to change, {plan.notes.kept_yours}{' '}
        kept as you wrote it
      </p>
      {nothing && <p>Nothing to add or change.</p>}
      <Issues label="Rows that will be skipped" items={plan.skipped} />
      <Issues label="Rows that were shortened" items={plan.shortened} />
      {error && (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}
      <div className="flex gap-2">
        <Button type="button" size="sm" disabled={busy || nothing} onClick={onConfirm}>
          Confirm import
        </Button>
        <Button type="button" variant="ghost" size="sm" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </section>
  )
}

/** Import a company sheet saved as CSV: a preview first, and nothing is saved until Confirm. */
export function SheetImportDialog() {
  const [open, setOpen] = useState(false)
  const [done, setDone] = useState<string | null>(null)
  const preview = useSheetPreview()
  const confirm = useSheetConfirm()
  const plan = preview.data && !confirm.isSuccess ? preview.data : null
  const trigger = useRef<HTMLButtonElement>(null)
  const fileInput = useRef<HTMLInputElement>(null)
  const wasOpen = useRef(false)

  // Keyboard and screen-reader users follow the focus: into the dialog, and back on close.
  useEffect(() => {
    if (open) fileInput.current?.focus()
    else if (wasOpen.current) trigger.current?.focus()
    wasOpen.current = open
  }, [open])

  function close() {
    preview.reset()
    confirm.reset()
    setOpen(false)
  }

  if (!open) {
    return (
      <div className="space-y-2">
        <Button
          ref={trigger}
          type="button"
          variant="outline"
          size="sm"
          onClick={() => setOpen(true)}
        >
          Import a company sheet
        </Button>
        {done && <p role="status">{done}</p>}
      </div>
    )
  }

  const seen = headersSeen(preview.error)
  return (
    <div
      role="dialog"
      aria-label="Import a company sheet"
      className="space-y-3"
      onKeyDown={(event) => {
        if (event.key === 'Escape') close()
      }}
    >
      <p className="text-sm text-muted-foreground">
        Save your spreadsheet as a CSV file and choose it here. Contacts and notes stay on this
        computer and are never sent to an AI.
      </p>
      <label className="block text-sm font-medium">
        Company sheet (CSV)
        <input
          ref={fileInput}
          type="file"
          accept=".csv,text/csv"
          className="ml-2 text-sm"
          onChange={(event) => {
            const file = event.target.files?.[0]
            event.target.value = ''
            if (!file) return
            setDone(null)
            confirm.reset()
            preview.mutate(file)
          }}
        />
      </label>
      {preview.isError && (
        <p role="alert" className="text-sm text-danger">
          {preview.error.message}
          {seen.length > 0 && ` Columns in the file: ${seen.join(', ')}.`}
        </p>
      )}
      {plan && (
        <Preview
          plan={plan}
          busy={confirm.isPending}
          error={confirm.isError ? confirm.error.message : null}
          onCancel={close}
          onConfirm={() =>
            confirm.mutate(plan.token, {
              onSuccess: (result) => {
                setDone(resultText(result))
                preview.reset()
                setOpen(false)
              },
            })
          }
        />
      )}
      {!plan && (
        <Button type="button" variant="ghost" size="sm" onClick={close}>
          Cancel
        </Button>
      )}
    </div>
  )
}
