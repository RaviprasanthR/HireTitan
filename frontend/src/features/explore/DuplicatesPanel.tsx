import { Button } from '@/components/ui/button'
import { type JobCard, formatDate, useDecideDuplicate, useDuplicates } from './api'

function Side({ job }: { job: JobCard }) {
  return (
    <div className="min-w-0 flex-1 space-y-1">
      <p className="font-medium">{job.title}</p>
      <p className="text-sm text-muted-small">
        {[job.company_name, job.location_text, job.posted_at ? formatDate(job.posted_at) : null]
          .filter(Boolean)
          .join(' · ')}
      </p>
      {job.sources.map((source) => (
        <a
          key={source.url}
          href={source.url}
          target="_blank"
          rel="noreferrer noopener"
          className="block truncate text-sm text-link underline"
        >
          {source.url}
        </a>
      ))}
    </div>
  )
}

/** Pairs the search thinks may be the same job. Nothing merges unless the person says so (FR-021). */
export function DuplicatesPanel() {
  const pairs = useDuplicates()
  const decide = useDecideDuplicate()
  const items = pairs.data?.items ?? []
  if (items.length === 0) return null
  return (
    <section aria-label="Possible duplicates" className="space-y-3 rounded-lg bg-surface p-4">
      <h2 className="text-base font-semibold">Possible duplicates</h2>
      <p className="text-sm text-muted-small">These look like the same job. You decide.</p>
      <ul className="space-y-3">
        {items.map((pair) => (
          <li key={pair.id} className="space-y-2 border-t border-divider pt-3">
            <div className="flex flex-wrap gap-4">
              <Side job={pair.job_a} />
              <Side job={pair.job_b} />
            </div>
            <div className="flex gap-2">
              <Button
                type="button"
                size="sm"
                disabled={decide.isPending}
                onClick={() => decide.mutate({ id: pair.id, action: 'merge' })}
              >
                Merge
              </Button>
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={decide.isPending}
                onClick={() => decide.mutate({ id: pair.id, action: 'dismiss' })}
              >
                Not the same
              </Button>
            </div>
          </li>
        ))}
      </ul>
      {decide.isError && (
        <p role="alert" className="text-sm text-danger">
          {decide.error.message}
        </p>
      )}
    </section>
  )
}
