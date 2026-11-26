import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { CircularProgress } from '@/components/CircularProgress'
import { Button } from '@/components/ui/button'
import { nextPhrase } from './phrases'
import { MailFlow, OutcomeDonut, SearchFlow } from './SearchFlow'
import {
  type RunSummary,
  useLatestRun,
  useMailConnection,
  useStartMailCheck,
  useStartSearch,
  useStopSearch,
} from './api'

const ENDED: Record<string, string> = {
  finished: 'Search finished.',
  stopped_by_user: 'Search stopped. Jobs found so far are kept.',
  // a search that ended under the old AI budget (no longer in HireTitan)
  budget_reached: 'Search stopped. Jobs found so far are kept.',
  out_of_credit:
    'Your AI account is out of credit, so the search stopped. Jobs found so far are kept.',
  failed: 'The search stopped because of an error. Jobs found so far are kept.',
}

const ENDED_MAIL: Record<string, string> = {
  finished: 'Mail check finished.',
  stopped_by_user: 'Mail check stopped. Jobs found so far are kept.',
  failed: 'Mail check stopped before it could finish. Jobs found so far are kept.',
}

const isMailRun = (run: RunSummary | null) => run?.mode === 'mail_alerts'

/** Emails the check had not read before, and how far it has got. */
function mailProgress(run: RunSummary) {
  const mail = run.mail
  const fresh = mail ? Math.max(0, mail.emails_listed - mail.emails_skipped) : 0
  const done = mail ? mail.emails_read + mail.emails_unreadable : 0
  return { mail, fresh, done }
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
  const mailRun = isMailRun(run)
  const mailNow = run && mailRun ? mailProgress(run) : null
  const started = mailNow
    ? mailNow.done > 0 && mailNow.fresh > 0
    : run !== null && run.companies_total > 0 && run.companies_read > 0
  const percent =
    started && run
      ? mailNow
        ? Math.min(100, Math.round((mailNow.done / mailNow.fresh) * 100))
        : Math.round((run.companies_read / run.companies_total) * 100)
      : null
  const [phrase, setPhrase] = useState(() => nextPhrase(null))
  useEffect(() => {
    if (stopping) return
    const timer = window.setInterval(() => setPhrase((was) => nextPhrase(was)), 3500)
    return () => window.clearInterval(timer)
  }, [stopping])
  return (
    <div className="flex items-center gap-4">
      <CircularProgress
        label={mailRun ? 'Mail check progress' : 'Search progress'}
        value={percent}
        animated={!stopping}
      />
      <div className="min-w-0 space-y-1.5">
        {/* a changing phrase is decoration: it is hidden from screen readers, which hear the
            one steady status line above instead */}
        {!stopping && (
          <p aria-hidden className="text-sm italic text-muted-small">
            {phrase}
          </p>
        )}
        {started && run && mailNow?.mail && (
          <p className="text-sm text-muted-small">
            {`Read ${mailNow.mail.emails_read} of ${mailNow.fresh} new emails${
              mailNow.mail.emails_unreadable > 0
                ? ` (${mailNow.mail.emails_unreadable} could not be read)`
                : ''
            } · ${run.added} new jobs so far`}
          </p>
        )}
        {started && run && !mailNow && (
          <p className="text-sm text-muted-small">{counts(run, ' so far')}</p>
        )}
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

/** What the last search or mail check said when it ended, under the actions. Its flow is in the
 * overview beside the list (`SearchOverview`). A search that ended before it had companies to
 * read only says how many new jobs it found. */
function Ended({ run }: { run: RunSummary }) {
  const mail = run.mail
  if (run.mode === 'mail_alerts' && mail) {
    if (!run.stop_message && mail.ended !== 'access_ended') return null
    return (
      <div className="space-y-3">
        {run.stop_message && <p className="text-sm">{run.stop_message}</p>}
        {mail.ended === 'access_ended' && (
          <p className="text-sm">
            <Link to="/settings/gmail" className="text-link underline">
              Open Settings to connect Gmail again
            </Link>
          </p>
        )}
      </div>
    )
  }
  if (!run.stop_message && run.companies_total > 0 && !run.ai_note) return null
  return (
    <div className="space-y-3">
      {run.stop_message && <p className="text-sm">{run.stop_message}</p>}
      {run.companies_total === 0 && <p className="text-sm text-muted-small">{counts(run, '')}</p>}
      {run.ai_note && <p className="text-sm text-warning">{run.ai_note}</p>}
    </div>
  )
}

/** The overview's line while a running search has nothing read yet. */
function FillsIn({ what }: { what: 'companies' | 'emails' }) {
  return (
    <p className="ht-detail-card text-sm text-muted-small">
      The flow fills in as {what} are read.
    </p>
  )
}

/** The latest search or mail check as a flow, for the overview beside the Explore list (FR-023a).
 * A running search shows its flow filling in, so the overview keeps its column and the table stays
 * beside it; the donut of what happened to the jobs found follows once it has ended. Nothing before
 * the first search. */
export function SearchOverview() {
  const run = useLatestRun().data ?? null
  if (!run) return null
  const live = run.outcome === null
  const mail = run.mail
  if (run.mode === 'mail_alerts' && mail) {
    // never "0 of 9" while the first email is being read (US2 AS1)
    if (live && mail.emails_read + mail.emails_unreadable === 0) return <FillsIn what="emails" />
    return (
      <>
        <MailFlow
          counts={{
            emailsRead: mail.emails_read,
            emailsNew: Math.max(0, mail.emails_listed - mail.emails_skipped),
            unreadable: mail.emails_unreadable,
            alreadyRead: mail.emails_skipped,
            jobsFound: run.jobs_found,
            byRules: run.skipped_by_rules,
            added: run.added,
            merged: run.merged,
          }}
        />
        {!live && (
          <OutcomeDonut
            compact
            added={run.added}
            merged={run.merged}
            leftOut={run.skipped_by_rules}
          />
        )}
      </>
    )
  }
  if (run.companies_total === 0 || (live && run.companies_read === 0))
    return live ? <FillsIn what="companies" /> : null
  const leftOutByAi = Math.max(0, run.judged_by_ai - run.kept)
  return (
    <>
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
      {!live && (
        <OutcomeDonut
          compact
          added={run.added}
          merged={run.merged}
          leftOut={run.skipped_by_rules + leftOutByAi}
        />
      )}
    </>
  )
}

export function SearchPanel() {
  const latest = useLatestRun()
  const start = useStartSearch()
  const startMail = useStartMailCheck()
  const connection = useMailConnection()
  const stop = useStopSearch()
  // The run that was the latest when "Search now" was pressed. Until a different run shows up (or
  // the start fails, or the server has answered and the latest run is read again) the panel is
  // already searching, so there is no moment that looks idle or shows "0 of 0" (US2 AS1).
  const [clicked, setClicked] = useState<{
    base: string | null
    mail: boolean
  } | null>(null)
  const launcher = clicked?.mail ? startMail : start
  const run = latest.data ?? null
  const active = run !== null && run.outcome === null
  const resumable =
    run != null &&
    !isMailRun(run) &&
    ['stopped_by_user', 'budget_reached', 'out_of_credit', 'failed'].includes(run.outcome ?? '')
  const starting =
    clicked !== null &&
    !launcher.isError &&
    (run?.id ?? null) === clicked.base &&
    !(launcher.isSuccess && !latest.isFetching)
  const searching = active || starting
  const stopping = active && run !== null && (run.stop_requested || stop.isSuccess)

  const begin = () => {
    stop.reset() // a stop pressed on the last run is not this run's
    start.reset()
    startMail.reset()
    setClicked({ base: run?.id ?? null, mail: false })
    start.mutate('rules_and_ai') // the AI always judges; without a working key the jobs say so
  }
  const beginMail = () => {
    stop.reset()
    start.reset()
    startMail.reset()
    setClicked({ base: run?.id ?? null, mail: true })
    startMail.mutate()
  }
  // what the panel is doing now: the button just pressed while starting, else the active run
  const watching = starting ? clicked?.mail === true : active && isMailRun(run)

  // One status line that is always on the page, so a screen reader announces each change of it
  // (a live region that arrives together with its text is often not announced).
  const message = searching
    ? stopping
      ? 'Stopping… jobs found so far are kept.'
      : watching
        ? 'Reading your job-alert mail…'
        : 'Searching your companies…'
    : run
      ? isMailRun(run)
        ? (ENDED_MAIL[run.outcome ?? ''] ?? 'Mail check ended.')
        : (ENDED[run.outcome ?? ''] ?? 'Search ended.')
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
            {connection.data?.state === 'connected' && (
              <Button
                type="button"
                variant="outline"
                disabled={startMail.isPending}
                onClick={beginMail}
              >
                Check job-alert mail
              </Button>
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
      {launcher.isError && (
        <p role="alert" className="text-sm text-danger">
          {launcher.error.message}
        </p>
      )}
    </section>
  )
}
