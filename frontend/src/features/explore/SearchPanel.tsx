import { useState } from 'react'
import { Link } from 'react-router'
import { ProgressBar } from '@/components/ProgressBar'
import { Button } from '@/components/ui/button'
import { type RunSummary, useLatestRun, useStartSearch, useStopSearch } from './api'

/** Companies checked and new jobs found: the one line of progress the person needs. */
function counts(run: RunSummary, suffix: string): string {
  return `Checked ${run.companies_read} of ${run.companies_total} companies · ${run.added} new jobs${suffix}`
}

/**
 * A search in progress. `run` is missing for the moment between pressing "Search now" and the
 * server's first answer: the panel already says it is searching, with no counts (US2 AS1).
 */
function Searching({ run }: { run: RunSummary | null }) {
  const stop = useStopSearch()
  const stopping = run !== null && (run.stop_requested || stop.isSuccess)
  // Counts appear once a company has been checked; before that only the moving bar is shown.
  const started = run !== null && run.companies_total > 0 && run.companies_read > 0
  const percent =
    started && run ? Math.round((run.companies_read / run.companies_total) * 100) : null
  return (
    <div className="space-y-2" aria-live="polite">
      <p className="font-medium">
        {stopping ? 'Stopping… jobs found so far are kept.' : 'Searching your companies…'}
      </p>
      {started && run && <p className="text-sm text-muted-small">{counts(run, ' so far')}</p>}
      <ProgressBar
        label="Search progress"
        value={percent}
        animated={percent !== null && !stopping}
      />
      {run && !stopping && (
        <Button type="button" variant="danger" size="sm" onClick={() => stop.mutate(run.id)}>
          Stop
        </Button>
      )}
      {stop.isError && (
        <p role="alert" className="text-sm text-danger">
          {stop.error.message}
        </p>
      )}
    </div>
  )
}

function Ended({ run }: { run: RunSummary }) {
  const reasons: Record<string, string> = {
    finished: 'Search finished.',
    stopped_by_user: 'Search stopped. Jobs found so far are kept.',
    // a search that ended under the old AI budget (no longer in HireTitan)
    budget_reached: 'Search stopped. Jobs found so far are kept.',
    out_of_credit:
      'Your AI account is out of credit, so the search stopped. Jobs found so far are kept.',
    failed: 'The search stopped because of an error. Jobs found so far are kept.',
  }
  return (
    <div className="space-y-1" aria-live="polite">
      <p className="font-medium">{reasons[run.outcome ?? ''] ?? 'Search ended.'}</p>
      {run.stop_message && <p className="text-sm">{run.stop_message}</p>}
      <p className="text-sm text-muted-small">{counts(run, '')}</p>
      {run.ai_note && <p className="text-sm text-warning">{run.ai_note}</p>}
      <p className="flex gap-4 text-sm">
        <Link to={`/search/runs/${run.id}`} className="text-link underline">
          See the summary
        </Link>
        <Link to="/search/history" className="text-link underline">
          Search history
        </Link>
      </p>
    </div>
  )
}

export function SearchPanel() {
  const latest = useLatestRun()
  const start = useStartSearch()
  const [rulesOnly, setRulesOnly] = useState(false)
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
  const begin = () => {
    setClicked({ base: run?.id ?? null })
    start.mutate(rulesOnly ? 'rules_only' : 'rules_and_ai')
  }

  return (
    <section aria-label="Search" className="space-y-3 rounded-lg bg-surface p-4">
      {searching ? (
        <Searching run={active ? run : null} />
      ) : (
        run && <Ended run={run} />
      )}
      {!searching && (
        <div className="flex flex-wrap items-center gap-4">
          <Button type="button" variant="success" disabled={start.isPending} onClick={begin}>
            {resumable ? 'Continue searching' : 'Search now'}
          </Button>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={rulesOnly}
              onChange={(e) => setRulesOnly(e.target.checked)}
            />
            Rules only (no AI)
          </label>
        </div>
      )}
      {start.isError && (
        <p role="alert" className="text-sm text-danger">
          {start.error.message}
        </p>
      )}
    </section>
  )
}
