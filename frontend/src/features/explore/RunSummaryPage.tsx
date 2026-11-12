import { Link, useParams } from 'react-router'
import { Button } from '@/components/ui/button'
import { OUTCOME_LABELS, formatDate, useRestore, useRun, useSkipped } from './api'

function companyResult(result: string, jobs: number, error: string | null): string {
  switch (result) {
    case 'ok':
      return `${jobs} jobs`
    case 'no_jobs':
      return 'No jobs listed'
    case 'failed':
      return `Failed${error ? `: ${error}` : ''}`
    case 'blocked':
      return 'Blocked: the site does not allow automatic reading. Check manually.'
    case 'unreadable':
      return 'Could not be read. Check manually.'
    default:
      return result
  }
}

function SkippedJobs({ runId }: { runId: string }) {
  const skipped = useSkipped(runId)
  const restore = useRestore()
  const items = skipped.data?.pages.flatMap((page) => page.items) ?? []
  if (skipped.isPending) return <p>Loading…</p>
  if (items.length === 0) return <p>No jobs were left out in this search.</p>
  return (
    <>
      <ul aria-label="Skipped jobs" className="space-y-2">
        {items.map((job) => (
          <li
            key={job.id}
            className="flex flex-wrap items-center justify-between gap-3 rounded-lg bg-surface p-3"
          >
            <span className="min-w-0">
              <Link to={`/jobs/${job.id}`} className="font-medium text-link underline">
                {job.title}
              </Link>
              <span className="block text-sm text-muted-small">
                {job.company_name} · {job.decision?.reason}
              </span>
            </span>
            {job.state === 'skipped' ? (
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={restore.isPending}
                onClick={() => restore.mutate(job.id)}
              >
                Restore
              </Button>
            ) : (
              <span className="text-sm text-success">Restored</span>
            )}
          </li>
        ))}
      </ul>
      {skipped.hasNextPage && (
        <Button type="button" variant="outline" onClick={() => void skipped.fetchNextPage()}>
          Load more
        </Button>
      )}
    </>
  )
}

/** What one search found, read and left out, with the left-out jobs and a way to bring them back. */
export function RunSummaryPage() {
  const { id = '' } = useParams()
  const run = useRun(id)
  if (run.isPending) return <p>Loading…</p>
  if (run.isError) return <p role="alert">Could not load this search.</p>
  const data = run.data
  const leftOutByAi = Math.max(0, data.judged_by_ai - data.kept)
  return (
    <section className="space-y-4">
      <h1 className="text-2xl font-semibold">Search summary</h1>
      <div className="space-y-1 rounded-lg bg-surface p-4">
        <p className="font-medium">
          {formatDate(data.started_at)} ·{' '}
          {data.outcome ? (OUTCOME_LABELS[data.outcome] ?? data.outcome) : 'Running'}
        </p>
        <p>
          {data.jobs_found} jobs found · {data.added} added · {data.skipped_by_rules} left out by
          your rules · {leftOutByAi} left out by the AI · {data.merged} already known ·{' '}
          {data.not_checked_by_ai} not checked by AI
        </p>
        <p>
          {data.companies_read} of {data.companies_total} companies read
        </p>
        {data.ai_note && <p className="text-warning">{data.ai_note}</p>}
        {data.stop_message && <p>{data.stop_message}</p>}
      </div>

      <section aria-label="Companies" className="space-y-2">
        <h2 className="text-lg font-semibold">Companies</h2>
        <ul aria-label="Companies" className="space-y-1">
          {data.companies.map((company) => (
            <li key={company.company_id} className="flex flex-wrap justify-between gap-3 text-sm">
              <span className="font-medium">{company.company_name}</span>
              <span className={company.result === 'ok' ? '' : 'text-warning'}>
                {companyResult(company.result, company.jobs_found, company.error)}
              </span>
            </li>
          ))}
        </ul>
      </section>

      <section className="space-y-2">
        <h2 className="text-lg font-semibold">Left out in this search</h2>
        <SkippedJobs runId={id} />
      </section>

      <Link to="/search/history" className="text-sm text-link underline">
        Search history
      </Link>
    </section>
  )
}
