import { useState } from 'react'
import { Link, useParams } from 'react-router'
import { BackButton } from '@/components/BackButton'
import { ChartRow } from '@/components/FlowChart'
import { OutcomeDonut, SearchFlow } from './SearchFlow'
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

const NEEDS_A_LOOK = new Set(['failed', 'blocked', 'unreadable'])

function minutesBetween(start: string | null, end: string | null): string | null {
  if (!start || !end) return null
  const minutes = Math.round((Date.parse(end) - Date.parse(start)) / 60_000)
  if (!Number.isFinite(minutes) || minutes < 0) return null
  return minutes < 1 ? 'took under a minute' : `took ${minutes} min`
}

/** What one search found, read and left out: a flow of steps and a bar first, then the details
 * (companies to check, left-out jobs to restore, every company) on request. */
export function RunSummaryPage() {
  const { id = '' } = useParams()
  const run = useRun(id)
  const [details, setDetails] = useState(false)
  const [showLeftOut, setShowLeftOut] = useState(false)
  if (run.isPending) return <p>Loading…</p>
  if (run.isError) return <p role="alert">Could not load this search.</p>
  const data = run.data
  const leftOutByAi = Math.max(0, data.judged_by_ai - data.kept)
  const leftOut = data.skipped_by_rules + leftOutByAi
  const toCheck = data.companies.filter((company) => NEEDS_A_LOOK.has(company.result))
  const took = minutesBetween(data.started_at, data.finished_at)
  const outcome = data.outcome ? (OUTCOME_LABELS[data.outcome] ?? data.outcome) : 'Running'

  return (
    <section className="space-y-5">
      <BackButton to="/explore" />
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold">Search summary</h1>
          <p className="text-muted-small">
            {formatDate(data.started_at)} · {outcome}
            {took ? ` · ${took}` : ''}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            aria-expanded={details}
            aria-controls="search-details"
            onClick={() => setDetails(!details)}
          >
            {details ? 'Hide details' : 'Show details'}
          </Button>
          <Button asChild variant="ghost" size="sm">
            <Link to="/search/history">Search history</Link>
          </Button>
        </div>
      </header>

      <ChartRow>
        <SearchFlow
          counts={{
            companiesRead: data.companies_read,
            companiesTotal: data.companies_total,
            toCheck: toCheck.length,
            jobsFound: data.jobs_found,
            byRules: data.skipped_by_rules,
            judgedByAi: data.judged_by_ai,
            byAi: leftOutByAi,
            added: data.added,
            merged: data.merged,
          }}
        />
        <OutcomeDonut added={data.added} merged={data.merged} leftOut={leftOut} />
      </ChartRow>

      {(data.ai_note || data.stop_message) && (
        <div className="space-y-1 text-sm">
          {data.ai_note && <p className="text-warning">{data.ai_note}</p>}
          {data.stop_message && <p>{data.stop_message}</p>}
        </div>
      )}

      {details && (
        <div id="search-details" className="space-y-4">
          {data.not_checked_by_ai > 0 && (
            <p className="text-sm">
              {data.not_checked_by_ai} jobs were not checked by the AI and are listed anyway.
            </p>
          )}
          {toCheck.length > 0 && (
            <section className="space-y-2">
              <h2 className="text-lg font-semibold">Companies to check by hand</h2>
              <ul aria-label="Companies to check" className="space-y-1">
                {toCheck.map((company) => (
                  <li
                    key={company.company_id}
                    className="flex flex-wrap justify-between gap-3 rounded-md bg-surface px-3 py-2 text-sm"
                  >
                    <span className="font-medium">{company.company_name}</span>
                    <span className="text-warning">
                      {companyResult(company.result, company.jobs_found, company.error)}
                    </span>
                  </li>
                ))}
              </ul>
            </section>
          )}

          <details
            className="rounded-lg bg-surface p-3"
            onToggle={(event) => setShowLeftOut(event.currentTarget.open)}
          >
            <summary className="cursor-pointer font-medium">Jobs left out ({leftOut})</summary>
            <div className="mt-3">{showLeftOut && <SkippedJobs runId={id} />}</div>
          </details>

          <details className="rounded-lg bg-surface p-3">
            <summary className="cursor-pointer font-medium">
              All {data.companies.length} companies
            </summary>
            <ul aria-label="Companies" className="mt-3 space-y-1">
              {data.companies.map((company) => (
                <li
                  key={company.company_id}
                  className="flex flex-wrap justify-between gap-3 text-sm"
                >
                  <span>{company.company_name}</span>
                  <span className={company.result === 'ok' ? 'text-muted-small' : 'text-warning'}>
                    {companyResult(company.result, company.jobs_found, company.error)}
                  </span>
                </li>
              ))}
            </ul>
          </details>
        </div>
      )}
    </section>
  )
}
