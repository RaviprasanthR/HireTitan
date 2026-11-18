import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { CircularProgress } from '@/components/CircularProgress'
import { Button } from '@/components/ui/button'
import { nextPhrase } from './phrases'
import { ChartRow } from '@/components/FlowChart'
import { OutcomeDonut, SearchFlow } from './SearchFlow'
import { type RunSummary, useLatestRun, useStartSearch, useStopSearch } from './api'

const ENDED: Record<string, string> = {
  finished: 'Search finished.',
  stopped_by_user: 'Search stopped. Jobs found so far are kept.',
  // a search that ended under the old AI budget (no longer in HireTitan)
  budget_reached: 'Search stopped. Jobs found so far are kept.',
  out_of_credit:
    'Your AI account is out of credit, so the search stopped. Jobs found so far are kept.',
  failed: 'The search stopped because of an error. Jobs found so far are kept.',
}

/** Companies checked and new jobs found: the one line of progress the person needs. */
function counts(run: RunSummary, suffix: string): string {
  const jobs = `${run.added} new jobs${suffix}`
  // a search that ended before its plan was made has no companies to count
  return run.companies_total > 0
    ? `Checked ${run.companies_read} of ${run.companies_total} companies · ${jobs}`
    : jobs
}

/**
 * Progress of a search that is running. `run` is missing for the moment between pressing
 * "Search now" and the server's first answer: the ring is already spinning, with no counts
 * (US2 AS1). Counts appear once a company has been checked, never as "0 of 20".
 */
function Progress({
  run,
  stopping,
  stop,
}: {
  run: RunSummary | null
  stopping: boolean
  stop: ReturnType<typeof useStopSearch>
}) {
  const started = run !== null && run.companies_total > 0 && run.companies_read > 0
  const percent =
    started && run ? Math.round((run.companies_read / run.companies_total) * 100) : null
  const [phrase, setPhrase] = useState(() => nextPhrase(null))
  useEffect(() => {
    if (stopping) return
    const timer = window.setInterval(() => setPhrase((was) => nextPhrase(was)), 3500)
    return () => window.clearInterval(timer)
  }, [stopping])
  return (
    <div className="flex items-center gap-4">
      <CircularProgress label="Search progress" value={percent} animated={!stopping} />
      <div className="min-w-0 space-y-1.5">
        {/* a changing phrase is decoration: it is hidden from screen readers, which hear the
            one steady status line above instead */}
        {!stopping && (
          <p aria-hidden className="text-sm italic text-muted-small">
            {phrase}
          </p>
        )}
        {started && run && <p className="text-sm text-muted-small">{counts(run, ' so far')}</p>}
        {run && !stopping && (
          <Button
            type="button"
            variant="danger"
            size="sm"
            disabled={stop.isPending}
            onClick={() => stop.mutate(run.id)}
          >
            Stop
          </Button>
        )}
        {stop.isError && (
          <p role="alert" className="text-sm text-danger">
            {stop.error.message}
          </p>
        )}
      </div>
    </div>
  )
}

/** The last search at the top of Explore: the same flow and bar as its summary page, with links
 * to the full summary and the history. A search that ended before it had companies to read only
 * says how many new jobs it found. */
function Ended({ run }: { run: RunSummary }) {
  const leftOutByAi = Math.max(0, run.judged_by_ai - run.kept)
  return (
    <div className="space-y-3">
      {run.stop_message && <p className="text-sm">{run.stop_message}</p>}
      {run.companies_total > 0 ? (
        <ChartRow>
          <SearchFlow
            counts={{
              companiesRead: run.companies_read,
              companiesTotal: run.companies_total,
              toCheck: 0, // the latest-search answer has no per-company results; the summary does
              jobsFound: run.jobs_found,
              byRules: run.skipped_by_rules,
              judgedByAi: run.judged_by_ai,
              byAi: leftOutByAi,
              added: run.added,
              merged: run.merged,
            }}
          />
          <OutcomeDonut
            added={run.added}
            merged={run.merged}
            leftOut={run.skipped_by_rules + leftOutByAi}
          />
        </ChartRow>
      ) : (
        <p className="text-sm text-muted-small">{counts(run, '')}</p>
      )}
      {run.ai_note && <p className="text-sm text-warning">{run.ai_note}</p>}
    </div>
  )
}

export function SearchPanel() {
  const latest = useLatestRun()
  const start = useStartSearch()
  const stop = useStopSearch()
  // The run that was the latest when "Search now" was pressed. Until a different run shows up (or
  // the start fails, or the server has answered and the latest run is read again) the panel is
  // already searching, so there is no moment that looks idle or shows "0 of 0" (US2 AS1).
  const [clicked, setClicked] = useState<{ base: string | null } | null>(null)
  const run = latest.data ?? null
  const active = run !== null && run.outcome === null
  const resumable =
    run != null &&
    ['stopped_by_user', 'budget_reached', 'out_of_credit', 'failed'].includes(run.outcome ?? '')
  const starting =
    clicked !== null &&
    !start.isError &&
    (run?.id ?? null) === clicked.base &&
    !(start.isSuccess && !latest.isFetching)
  const searching = active || starting
  const stopping = active && run !== null && (run.stop_requested || stop.isSuccess)

  const begin = () => {
    setClicked({ base: run?.id ?? null })
    start.mutate('rules_and_ai') // the AI always judges; without a working key the jobs say so
  }

  // One status line that is always on the page, so a screen reader announces each change of it
  // (a live region that arrives together with its text is often not announced).
  const message = searching
    ? stopping
      ? 'Stopping… jobs found so far are kept.'
      : 'Searching your companies…'
    : run
      ? (ENDED[run.outcome ?? ''] ?? 'Search ended.')
      : ''

  return (
    <section aria-label="Search" className="ht-search-panel space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p role="status" aria-live="polite" className="font-medium empty:hidden">
          {message}
        </p>
        {!searching && (
          <div className="ml-auto flex flex-wrap items-center gap-2">
            {run && (
              <>
                <Button asChild variant="ghost" size="sm">
                  <Link to={`/search/runs/${run.id}`}>See the summary</Link>
                </Button>
                <Button asChild variant="ghost" size="sm">
                  <Link to="/search/history">Search history</Link>
                </Button>
              </>
            )}
            <Button type="button" variant="success" disabled={start.isPending} onClick={begin}>
              {resumable ? 'Continue searching' : 'Search now'}
            </Button>
          </div>
        )}
      </div>
      {searching ? (
        <Progress run={active ? run : null} stopping={stopping} stop={stop} />
      ) : (
        run && <Ended run={run} />
      )}
      {start.isError && (
        <p role="alert" className="text-sm text-danger">
          {start.error.message}
        </p>
      )}
    </section>
  )
}
