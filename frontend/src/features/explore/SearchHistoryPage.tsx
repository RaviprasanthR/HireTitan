import { Link } from 'react-router'
import { Button } from '@/components/ui/button'
import { OUTCOME_LABELS, formatDate, useRuns } from './api'

/** Every search with its date, outcome, counts and cost (FR-042). */
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
              <p className="font-medium">
                {formatDate(run.started_at)} ·{' '}
                {run.outcome ? (OUTCOME_LABELS[run.outcome] ?? run.outcome) : 'Running'}
              </p>
              <p className="text-sm text-muted-small">
                {run.jobs_found} jobs found · {run.added} jobs added · {run.companies_read} of{' '}
                {run.companies_total} companies read · AI cost: $
                {Number(run.ai_cost_usd).toFixed(4)}
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
      <h1 className="text-2xl font-semibold">Search history</h1>
      {body}
    </section>
  )
}
