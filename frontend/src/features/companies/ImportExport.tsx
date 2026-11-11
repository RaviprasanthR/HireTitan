import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { EXPORT_URL, useConfirmImport, usePreviewImport } from './api'
import { SheetImportDialog } from './SheetImportDialog'

/** Export the company list, or import one: a preview first, and nothing changes until Confirm. */
export function ImportExport() {
  const preview = usePreviewImport()
  const confirm = useConfirmImport()
  const [done, setDone] = useState<string | null>(null)
  const [withContacts, setWithContacts] = useState(false)
  const plan = preview.data && !confirm.isSuccess ? preview.data : null

  function reset() {
    preview.reset()
    confirm.reset()
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-3">
        <a
          href={withContacts ? `${EXPORT_URL}?include_contacts=true` : EXPORT_URL}
          download
          className="text-sm font-medium text-link underline"
        >
          Export CSV
        </a>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={withContacts}
            onChange={(event) => setWithContacts(event.target.checked)}
          />
          Include contacts and notes
        </label>
        <label className="text-sm font-medium">
          Import CSV
          <input
            type="file"
            accept=".csv,text/csv"
            className="ml-2 text-sm"
            onChange={(event) => {
              const file = event.target.files?.[0]
              event.target.value = ''
              if (!file) return
              setDone(null)
              reset()
              preview.mutate(file)
            }}
          />
        </label>
      </div>
      <p className="text-sm text-muted-small">
        With contacts and notes, the file will hold other people&apos;s details (names, emails,
        phones). Keep it private.
      </p>
      <SheetImportDialog />
      {preview.isError && (
        <p role="alert" className="text-sm text-danger">
          {preview.error.message}
        </p>
      )}
      {done && <p role="status">{done}</p>}
      {plan && (
        <section aria-label="Import preview" className="space-y-3 rounded-lg bg-surface p-4">
          <p className="font-medium">
            {plan.add.length} to add, {plan.update.length} to update, {plan.invalid.length} cannot
            be used.
          </p>
          {plan.add.length > 0 && (
            <ul aria-label="To add" className="list-disc pl-5 text-sm">
              {plan.add.map((row) => (
                <li key={row.row}>
                  {row.name}
                  {row.city ? ` · ${row.city}` : ''}
                </li>
              ))}
            </ul>
          )}
          {plan.update.length > 0 && (
            <ul aria-label="To update" className="list-disc pl-5 text-sm">
              {plan.update.map((row) => (
                <li key={row.row}>
                  {row.name}:{' '}
                  {Object.entries(row.changes)
                    .map(([field, change]) => `${field.replace('_', ' ')} ${change.from ?? '—'} → ${change.to}`)
                    .join('; ')}
                </li>
              ))}
            </ul>
          )}
          {plan.invalid.length > 0 && (
            <ul aria-label="Cannot be used" className="list-disc pl-5 text-sm text-danger">
              {plan.invalid.map((row) => (
                <li key={`${row.row}-${row.reason}`}>
                  Row {row.row}: {row.reason}
                </li>
              ))}
            </ul>
          )}
          {confirm.isError && (
            <p role="alert" className="text-sm text-danger">
              {confirm.error.message}
            </p>
          )}
          <div className="flex gap-2">
            <Button
              type="button"
              size="sm"
              disabled={confirm.isPending || plan.add.length + plan.update.length === 0}
              onClick={() =>
                confirm.mutate(plan.token, {
                  onSuccess: (result) => {
                    setDone(`Added ${result.added} and updated ${result.updated}.`)
                    preview.reset()
                  },
                })
              }
            >
              Confirm import
            </Button>
            <Button type="button" variant="ghost" size="sm" onClick={reset}>
              Cancel
            </Button>
          </div>
        </section>
      )}
    </div>
  )
}
