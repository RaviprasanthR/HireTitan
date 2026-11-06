import { Link } from 'react-router'
import { Button } from '@/components/ui/button'
import { formatDay, useAppliedJobs } from '@/features/explore/api'
import { useUndoApplied } from './appliedApi'

/** Every job marked as applied, newest application first. */
export function AppliedPage() {
  const jobs = useAppliedJobs()
  const undo = useUndoApplied()
  const items = jobs.data?.pages.flatMap((page) => page.items) ?? []

  let body
  if (jobs.isPending) body = <p>Loading…</p>
  else if (jobs.isError) body = <p role="alert">Could not load your applied jobs.</p>
  else if (items.length === 0) body = <p>You haven’t marked any job as applied yet.</p>
  else
    body = (
      <>
        <ul aria-label="Applied jobs" className="space-y-3">
          {items.map((job) => (
            <li
              key={job.id}
              className="flex items-start justify-between gap-4 rounded-lg bg-surface p-4"
            >
              <div className="space-y-1">
                <Link
                  to={`/jobs/${job.id}`}
                  className="text-base font-semibold text-link underline"
                >
                  {job.title}
                </Link>
                <p className="text-sm text-muted-small">
                  {[job.company_name, job.location_text].filter(Boolean).join(' · ')}
                </p>
                <p className="text-sm">Applied {formatDay(job.applied_on)}</p>
              </div>
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={undo.isPending}
                onClick={() => undo.mutate(job.id)}
              >
                Undo
              </Button>
            </li>
          ))}
        </ul>
        {jobs.hasNextPage && (
          <Button
            type="button"
            variant="outline"
            disabled={jobs.isFetchingNextPage}
            onClick={() => void jobs.fetchNextPage()}
          >
            Load more
          </Button>
        )}
      </>
    )

  return (
    <section className="space-y-4">
      <h1 className="text-2xl font-semibold">Applied</h1>
      {undo.isError && (
        <p role="alert" className="text-sm text-danger">
          {undo.error.message}
        </p>
      )}
      {body}
    </section>
  )
}
