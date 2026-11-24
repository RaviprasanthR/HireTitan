import { ChevronRight, CircleCheck } from 'lucide-react'
import { Fragment, useId, useState } from 'react'
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
import { SOURCE_TONE } from './pillTones'
import { SearchPanel } from './SearchPanel'
import {
  type JobCard,
  type JobFilters,
  NO_FILTERS,
  formatDate,
  isNotChecked,
  reasonOf,
  siteLabel,
  sourceLabel,
  useJobs,
  useRecheck,
} from './api'

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
export function JobCardItem({ job, showCheck = true }: { job: JobCard; showCheck?: boolean }) {
  const recheck = useRecheck()
  const [open, setOpen] = useState(false)
  const panelId = useId()
  const source = job.sources[0]
  const href = postingLink(source?.url)
  const where = [job.location_text, job.work_mode].filter(Boolean).join(' · ')

  return (
    <Fragment>
      <tr className="ht-row border-t border-divider align-top">
        <td className="px-3 py-2">{job.company_name}</td>
        <td className="px-3 py-2">
          {href ? (
            <a
              href={href}
              target="_blank"
              rel="noreferrer noopener"
              title={job.title}
              className="block max-w-[22rem] truncate font-semibold text-link underline"
            >
              {job.title}
            </a>
          ) : (
            <span title={job.title} className="block max-w-[22rem] truncate font-semibold">
              {job.title}
            </span>
          )}
          {job.may_have_closed && (
            <p className="mt-0.5">
              <Pill tone="yellow">May have closed</Pill>
            </p>
          )}
          {reasonOf(job) && (
            <p className="mt-0.5 max-w-[22rem] text-xs text-muted-small">{reasonOf(job)}</p>
          )}
          {showCheck && isNotChecked(job) && (
            <div className="mt-1 flex items-center gap-3">
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={recheck.isPending || recheck.isSuccess}
                onClick={() => recheck.mutate(job.id)}
              >
                Check again
              </Button>
              {recheck.isSuccess && (
                <span className="text-sm text-muted-small">Checking with the AI…</span>
              )}
              {recheck.isError && (
                <span role="alert" className="text-sm text-danger">
                  {recheck.error.message}
                </span>
              )}
            </div>
          )}
        </td>
        <td className="px-3 py-2">{where || '—'}</td>
        <td className="px-3 py-2 whitespace-nowrap">
          {job.posted_at ? formatDate(job.posted_at) : '—'}
        </td>
        <td className="px-3 py-2">
          {source ? (
            <>
              <Pill tone={SOURCE_TONE[sourceLabel(source.kind).toLowerCase()] ?? 'grey'}>
                {sourceLabel(source.kind)}
              </Pill>
              {source.kind === 'email_alert' && source.site && (
                <span className="block text-xs text-muted-small">{siteLabel(source.site)}</span>
              )}
            </>
          ) : (
            '—'
          )}
        </td>
        <td className="px-3 py-2">
          <div className="flex items-start justify-end gap-2">
            <PipelineControl
              id={job.id}
              state={job.state}
              title={job.title}
              className="justify-end"
              compact
            />
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
        <tr>
          <td id={panelId} colSpan={COLUMNS.length + 1} className="space-y-4 bg-surface px-4 py-3">
            {(job.state === 'explore' || job.state === 'inquired') && (
              <Section
                title="Record it"
                icon={CircleCheck}
                tone="ht-section-record"
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
      className="flex flex-wrap items-end gap-3"
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
        <div className="overflow-x-auto rounded-lg bg-surface">
          <table aria-label="Jobs" className="w-full text-left text-sm">
            <thead className="ht-thead">
              <tr>
                {COLUMNS.map((name) => (
                  <th key={name} scope="col" className="px-3 py-3">
                    {name}
                  </th>
                ))}
                <th scope="col" aria-label="Actions" className="px-3 py-2" />
              </tr>
            </thead>
            <tbody>
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
    <section className="space-y-4">
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
      <Filters value={filters} onChange={setFilters} />
      {list}
    </section>
  )
}
