import { useState } from 'react'
import { Link } from 'react-router'
import { Button } from '@/components/ui/button'
import { BATCH_SIZE, type RunSummary, useLatestRun, useStartSearch, useStopSearch } from './api'

function usd(value: string): string {
  return `$${Number(value).toFixed(4)}`
}

function Counts({ run }: { run: RunSummary }) {
  return (
    <p className="text-sm text-muted-small">
      {run.companies_read} of {run.companies_total} companies read · {run.added} jobs added ·{' '}
      {run.skipped_by_rules + (run.judged_by_ai - run.kept)} left out · AI cost so far:{' '}
      {usd(run.ai_cost_usd)}
    </p>
  )
}

function Progress({ run }: { run: RunSummary }) {
  const stop = useStopSearch()
  const batches = Math.max(1, Math.ceil(run.companies_total / BATCH_SIZE))
  const stopping = run.stop_requested || stop.isSuccess
  return (
    <div className="space-y-2" aria-live="polite">
      <p className="font-medium">
        Batch {Math.min(run.batches_done + 1, batches)} of {batches}
      </p>
      <Counts run={run} />
      {stopping ? (
        <p className="text-sm text-warning">Stopping after this batch…</p>
      ) : (
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
    stopped_by_user: 'Search stopped. Finished batches are kept.',
    budget_reached:
      'Your monthly AI budget was reached, so the search stopped. Finished batches are kept.',
    out_of_credit:
      'Your AI account is out of credit, so the search stopped. Finished batches are kept.',
    failed: 'The search stopped because of an error. Finished batches are kept.',
  }
  return (
    <div className="space-y-1">
      <p className="font-medium">{reasons[run.outcome ?? ''] ?? 'Search ended.'}</p>
      {run.stop_message && <p className="text-sm">{run.stop_message}</p>}
      <Counts run={run} />
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
  const run = latest.data
  const active = run != null && run.outcome === null
  const resumable =
    run != null &&
    ['stopped_by_user', 'budget_reached', 'out_of_credit', 'failed'].includes(run.outcome ?? '')

  return (
    <section aria-label="Search" className="space-y-3 rounded-lg bg-surface p-4">
      {run && (active ? <Progress run={run} /> : <Ended run={run} />)}
      {!active && (
        <div className="flex flex-wrap items-center gap-4">
          <Button
            type="button"
            variant="success"
            disabled={start.isPending}
            onClick={() => start.mutate(rulesOnly ? 'rules_only' : 'rules_and_ai')}
          >
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
