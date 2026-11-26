import { ChevronRight, CircleCheck } from 'lucide-react'
import { Fragment, useEffect, useId, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router'
import { useStatus } from '@/api/useStatus'
import { Button } from '@/components/ui/button'
import { ActOnJob } from '@/features/drafts/ActOnJob'
import { JobDetails } from '@/features/jobs/JobDetails'
import { PipelineControl } from '@/features/jobs/PipelineControl'
import { Section } from '@/features/jobs/Section'
import { PasteJobDialog } from '@/features/jobs/PasteJobDialog'
import { firstMissingStep, setupIsDone } from '@/features/home/setup'
import { DuplicatesPanel } from './DuplicatesPanel'
import { ReviewNotice } from '@/features/home/ReviewNotice'
import { HomeTabs } from './HomeTabs'
import { Pill } from './Pill'
import { SearchOverview, SearchPanel } from './SearchPanel'
import { OpenPosting } from '@/components/OpenPosting'
import { OverviewLayout } from '@/components/OverviewLayout'
import {
  type JobCard,
  type JobFilters,
  NO_FILTERS,
  formatDate,
  isNotChecked,
  newWorkMode,
  reasonOf,
  recheckJob,
  siteLabel,
  sourceLabel,
  useJobs,
  useRefreshing,
} from './api'

const jobsWord = (n: number) => `${n} ${n === 1 ? 'job' : 'jobs'}`

/**
 * The jobs the AI could not check for fit, gathered into one notice with one "Re-check fit" that
 * asks for each of them in turn and refreshes the list once at the end (FR-022). Rows only say why.
 */
function RecheckNotice({ jobs }: { jobs: JobCard[] }) {
  const refresh = useRefreshing()
  const section = useRef<HTMLElement>(null)
  // `total` is fixed when the run starts: the list may refetch while it runs
  const [state, setState] = useState<{
    running: boolean
    total: number
    failed: number
  } | null>(null)
  const none = jobs.length === 0
  useEffect(() => {
    // the button goes once every job is checked; keep focus in the notice, not on the page
    if (none && state && !state.running && document.activeElement === document.body)
      section.current?.focus()
  }, [none, state])
  if (none && state === null) return null
  const run = async () => {
    if (state?.running) return
    const batch = [...jobs]
    setState({ running: true, total: batch.length, failed: 0 })
    let failed = 0
    for (const job of batch) {
      try {
        await recheckJob(job.id)
      } catch {
        failed += 1
      }
    }
    try {
      await refresh()
    } finally {
      // never leave the button disabled, even if the refresh fails
      setState({ running: false, total: batch.length, failed })
    }
  }
  const total = state?.total ?? 0
  const sent = total - (state?.failed ?? 0)
  return (
    <section
      ref={section}
      tabIndex={-1}
      aria-label="Jobs not checked for fit"
      className="ht-card flex flex-wrap items-center gap-x-4 gap-y-2 p-4 text-sm"
    >
      {jobs.length > 0 && (
        <p className="min-w-0 flex-1">
          {jobsWord(jobs.length)} could not be checked for fit: no description yet
        </p>
      )}
      {jobs.length > 0 && (
        <Button
          type="button"
          variant="outline"
          size="sm"
          // aria-disabled, not disabled: the button keeps keyboard focus while the run goes on
          aria-disabled={state?.running || undefined}
          className="aria-disabled:opacity-50"
          onClick={() => void run()}
        >
          Re-check fit
        </Button>
      )}
      {/* both lines stay in the page so screen readers hear the text when it changes */}
      <div className="basis-full space-y-1">
        <p role="status" className="text-muted-small">
          {state?.running
            ? `Asking the AI to check ${jobsWord(total)}…`
            : state && sent > 0
              ? `Asked the AI to check ${jobsWord(sent)}. Their fit shows here once checked.`
              : ''}
        </p>
        <p role="alert" className="text-danger">
          {state && !state.running && state.failed > 0
            ? `${state.failed} of ${jobsWord(total)} could not be sent for a check. Try again later.`
            : ''}
        </p>
      </div>
    </section>
  )
}

const input = 'rounded-md border border-muted-foreground bg-background px-3 py-1.5 text-sm'

function postingLink(url: string | undefined): string | null {
  return url && /^https?:\/\//i.test(url) ? url : null
}

const COLUMNS = ['Company', 'Role', 'Location', 'Posted', 'Source'] as const

/**
 * One job as a row of the table, like the rows of the Applied list: company, role, where, when and
 * where it was found, with "I applied" and "I inquired" on the right. The arrow opens the row in
 * place to show the job's description and people; the role opens the posting itself in a new tab.
 */
export function JobCardItem({ job }: { job: JobCard }) {
  const [open, setOpen] = useState(false)
  const panelId = useId()
  const source = job.sources[0]
  const href = postingLink(source?.url)
  const location = job.location_text ?? ''
  const mode = newWorkMode(location, job.work_mode)

  return (
    <Fragment>
      <tr role="row" className="ht-row border-t border-divider align-top">
        <td role="cell" className="px-3 py-2">
          {job.company_name}
        </td>
        <td role="cell" className="px-3 py-2">
          {/* the title opens the job page; the posting has its own link with the actions (FR-019) */}
          <Link
            to={`/jobs/${job.id}`}
            title={job.title}
            className="block font-semibold text-link underline md:max-w-[22rem] xl:max-w-[13rem] min-[85rem]:max-w-[18rem] md:truncate"
          >
            {job.title}
          </Link>
          {job.may_have_closed && (
            <p className="mt-0.5">
              <Pill tone="yellow">May have closed</Pill>
            </p>
          )}
          {reasonOf(job) && (
            <p className="mt-0.5 max-w-[22rem] xl:max-w-[13rem] min-[85rem]:max-w-[18rem] text-xs text-muted-small">
              {reasonOf(job)}
            </p>
          )}
        </td>
        <td role="cell" data-label="Location" className="px-3 py-2">
          {location || mode ? (
            <>
              {location && <span className="block">{location}</span>}
              {mode && <span className="block text-muted-small">{mode}</span>}
            </>
          ) : (
            <span className="text-muted-small">Not set</span>
          )}
        </td>
        <td role="cell" data-label="Posted" className="px-3 py-2 whitespace-nowrap">
          {job.posted_at ? formatDate(job.posted_at) : <span className="text-muted-small">Not set</span>}
        </td>
        <td role="cell" data-label="Source" className="px-3 py-2">
          {source ? (
            <>
              <Pill tone="grey">{sourceLabel(source.kind)}</Pill>
              {source.kind === 'email_alert' && source.site && (
                <span className="block text-xs text-muted-small">{siteLabel(source.site)}</span>
              )}
            </>
          ) : (
            <span className="text-muted-small">Not set</span>
          )}
        </td>
        <td role="cell" className="px-3 py-2">
          <div className="flex items-start justify-end gap-2">
            <PipelineControl
              id={job.id}
              state={job.state}
              title={job.title}
              className="justify-end"
              compact
            />
            {href && <OpenPosting href={href} title={job.title} iconOnly />}
            <button
              type="button"
              className="ht-icon-button"
              aria-expanded={open}
              aria-controls={open ? panelId : undefined}
              aria-label={`${open ? 'Hide' : 'Show'} details of ${job.title}`}
              title={open ? 'Hide details' : 'Show details'}
              onClick={() => setOpen((was) => !was)}
            >
              <ChevronRight
                aria-hidden
                className={`size-4 transition-transform ${open ? 'rotate-90' : ''}`}
              />
            </button>
          </div>
        </td>
      </tr>
      {open && (
        <tr role="row">
          <td
            role="cell"
            id={panelId}
            colSpan={COLUMNS.length + 1}
            className="space-y-4 bg-surface px-4 py-3"
          >
            {(job.state === 'explore' || job.state === 'inquired') && (
              <Section
                title="Record it"
                icon={CircleCheck}
                hint="Choose the resume you used or pick another date."
              >
                <PipelineControl id={job.id} state={job.state} title={job.title} />
              </Section>
            )}
            <ActOnJob jobId={job.id} title={job.title} />
            <JobDetails id={job.id} actions={false} />
          </td>
        </tr>
      )}
    </Fragment>
  )
}

function Filters({ value, onChange }: { value: JobFilters; onChange: (next: JobFilters) => void }) {
  const set = (patch: Partial<JobFilters>) => onChange({ ...value, ...patch })
  return (
    <form
      aria-label="Filters"
      className="grid grid-cols-1 gap-3 md:flex md:flex-wrap md:items-end"
      onSubmit={(e) => e.preventDefault()}
    >
      <label className="flex flex-col gap-1 text-sm">
        Source
        <select
          className={input}
          value={value.source}
          onChange={(e) => set({ source: e.target.value })}
        >
          <option value="">All sources</option>
          <option value="company_board">Company job board</option>
          <option value="careers_page">Careers page</option>
          <option value="paste">Added by you</option>
          <option value="email_alert">Email alerts</option>
        </select>
      </label>
      <label className="flex flex-col gap-1 text-sm">
        Work mode
        <select
          className={input}
          value={value.work_mode}
          onChange={(e) => set({ work_mode: e.target.value })}
        >
          <option value="">Any</option>
          <option value="remote">Remote</option>
          <option value="hybrid">Hybrid</option>
          <option value="onsite">On-site</option>
        </select>
      </label>
      <label className="flex flex-col gap-1 text-sm">
        City
        <input
          className={input}
          value={value.city}
          onChange={(e) => set({ city: e.target.value })}
        />
      </label>
      <label className="flex flex-col gap-1 text-sm">
        Sort by
        <select
          className={input}
          value={value.sort}
          onChange={(e) => set({ sort: e.target.value as JobFilters['sort'] })}
        >
          <option value="newest">Newest</option>
          <option value="company">Company</option>
        </select>
      </label>
    </form>
  )
}

/** Why there are no jobs yet: the first thing still to do, with a link to do it (FR-006). */
function MissingStep({ checklist }: { checklist: Parameters<typeof firstMissingStep>[0] }) {
  const step = firstMissingStep(checklist)
  if (!step) return <p>No jobs yet.</p>
  return (
    <p>
      No jobs yet. {step.missing}{' '}
      <Link to={step.to} className="text-link underline">
        {step.action}
      </Link>
    </p>
  )
}

export function ExplorePage() {
  const status = useStatus()
  const [params, setParams] = useSearchParams()
  const [picked, setPicked] = useState<JobFilters>(NO_FILTERS)
  // A company can arrive in the link; it is not typed in.
  const company_id = params.get('company_id') ?? ''
  const filters = { ...picked, company_id }
  const setFilters = (next: JobFilters) => setPicked(next)
  const [adding, setAdding] = useState(false)
  const jobs = useJobs(filters)
  const setupDone = setupIsDone(status.data?.checklist)
  const items = jobs.data?.pages.flatMap((page) => page.items) ?? []
  const filtered =
    filters.source !== '' || filters.work_mode !== '' || filters.city !== '' || company_id !== ''

  let list
  if (jobs.isPending || status.isPending) {
    list = <p>Loading…</p>
  } else if (jobs.isError) {
    list = <p role="alert">Could not load your jobs.</p>
  } else if (items.length === 0) {
    list = filtered ? (
      <p>No jobs match these filters.</p>
    ) : setupDone ? (
      <p>No jobs fetched yet. Search now.</p>
    ) : (
      <MissingStep checklist={status.data?.checklist} />
    )
  } else {
    list = (
      <>
        <div className="ht-table-scroll overflow-x-auto md:rounded-lg md:bg-surface">
          <table role="table" aria-label="Jobs" className="ht-table-cards w-full text-left text-sm">
            <thead role="rowgroup" className="ht-thead">
              <tr role="row">
                {COLUMNS.map((name) => (
                  <th role="columnheader" key={name} scope="col" className="px-3 py-3">
                    {name}
                  </th>
                ))}
                <th role="columnheader" scope="col" aria-label="Actions" className="px-3 py-2" />
              </tr>
            </thead>
            <tbody role="rowgroup">
              {items.map((job) => (
                <JobCardItem key={job.id} job={job} />
              ))}
            </tbody>
          </table>
        </div>
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
  }

  return (
    <section className="ht-fit-page space-y-4">
      <div className="flex items-center justify-between gap-4">
        <h1 className="text-2xl font-semibold">Jobs</h1>
        {!adding && (
          <Button type="button" variant="outline" size="sm" onClick={() => setAdding(true)}>
            Add a job
          </Button>
        )}
      </div>
      <ReviewNotice />
      <HomeTabs />
      {adding && <PasteJobDialog onClose={() => setAdding(false)} />}
      {setupDone && <SearchPanel />}
      {setupDone && <DuplicatesPanel />}
      {company_id && (
        <p className="flex items-center gap-2 text-sm">
          <span className="rounded-full bg-surface px-3 py-1">
            Company: {items[0]?.company_name ?? 'this company'}
          </span>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            aria-label="Remove the company filter"
            onClick={() => setParams({})}
          >
            ✕
          </Button>
        </p>
      )}
      <OverviewLayout label="Search overview" overview={setupDone ? <SearchOverview /> : null}>
        <RecheckNotice jobs={items.filter(isNotChecked)} />
        <Filters value={filters} onChange={setFilters} />
        {list}
      </OverviewLayout>
    </section>
  )
}
