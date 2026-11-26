import { Link } from 'react-router'
import { BackButton } from '@/components/BackButton'
import { Button } from '@/components/ui/button'
import { OUTCOME_LABELS, formatDate, useRuns } from './api'

/** Every search with its date, outcome and counts (FR-042). */
export function SearchHistoryPage() {
  const runs = useRuns()
  const items = runs.data?.pages.flatMap((page) => page.items) ?? []

  let body
  if (runs.isPending) body = <p>Loading…</p>
  else if (runs.isError) body = <p role="alert">Could not load your searches.</p>
  else if (items.length === 0) body = <p>No searches yet. Search from the Jobs page.</p>
  else {
    body = (
      <>
        <ul aria-label="Searches" className="space-y-3">
          {items.map((run) => (
            <li key={run.id} className="space-y-1 rounded-lg bg-surface p-4">
              {/* facts set apart by space, not dots (FR-007) */}
              <p className="flex flex-wrap gap-x-4 font-medium">
                <span>{formatDate(run.started_at)}</span>
                <span>{run.outcome ? (OUTCOME_LABELS[run.outcome] ?? run.outcome) : 'Running'}</span>
              </p>
              <p className="flex flex-wrap gap-x-4 text-sm text-muted-small">
                <span>{run.jobs_found} jobs found</span>
                <span>{run.added} jobs added</span>
                <span>
                  {run.companies_read} of {run.companies_total} companies read
                </span>
              </p>
              {run.ai_note && <p className="text-sm text-warning">{run.ai_note}</p>}
              <Link to={`/search/runs/${run.id}`} className="text-sm text-link underline">
                See the summary
              </Link>
            </li>
          ))}
        </ul>
        {runs.hasNextPage && (
          <Button type="button" variant="outline" onClick={() => void runs.fetchNextPage()}>
            Load more
          </Button>
        )}
      </>
    )
  }

  return (
    <section className="space-y-4">
      <BackButton to="/explore" />
      <h1 className="text-2xl font-semibold">Search history</h1>
      {body}
    </section>
  )
}
