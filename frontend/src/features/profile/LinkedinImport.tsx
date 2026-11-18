import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Upload } from 'lucide-react'
import { useRef } from 'react'
import { apiFetch } from '@/api/client'
import type { components } from '@/api/schema'
import { Button } from '@/components/ui/button'

type Result = components['schemas']['LinkedinImportOut']

/**
 * Reads LinkedIn's Connections.csv in the browser and sends its text to this install only. People
 * who work at a company on the list become its contacts; everyone else is left out.
 */
export function LinkedinImport({ className }: { className?: string }) {
  const client = useQueryClient()
  const input = useRef<HTMLInputElement>(null)
  const run = useMutation({
    mutationFn: async (file: File) =>
      apiFetch<Result>('/companies/contacts/linkedin-import', {
        method: 'POST',
        json: { csv: await file.text() },
      }),
    onSuccess: () => client.invalidateQueries({ queryKey: ['companies'] }),
  })
  const r = run.data
  return (
    <div className="flex flex-wrap items-center gap-2">
      <input
        ref={input}
        type="file"
        accept=".csv,text/csv"
        aria-label="LinkedIn Connections.csv"
        tabIndex={-1}
        className="sr-only"
        onChange={(event) => {
          const file = event.target.files?.[0]
          if (file) run.mutate(file)
          event.target.value = ''
        }}
      />
      <Button
        type="button"
        size="sm"
        variant="outline"
        className={className}
        disabled={run.isPending}
        onClick={() => input.current?.click()}
      >
        <Upload aria-hidden />
        {run.isPending ? 'Importing…' : 'Import LinkedIn connections'}
      </Button>
      {/* always mounted, so the result is announced when it arrives */}
      <span role="status" className="text-sm text-muted-small">
        {r && (
          <>
            Added {r.added} people at {r.companies_with_new_contacts} companies
            {r.already_there > 0 && `, ${r.already_there} already there`}; {r.skipped_companies}{' '}
            employers are not on your list.
            {r.invalid_rows > 0 && ` ${r.invalid_rows} rows had details that could not be kept.`}
            {r.truncated && ' The file was too long, so only the first 20,000 people were read.'}
          </>
        )}
      </span>
      {run.isError && (
        <span role="alert" className="text-sm text-danger">
          {run.error.message}
        </span>
      )}
    </div>
  )
}
