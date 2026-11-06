import { useState } from 'react'
import { Link } from 'react-router'
import { useStatus } from '@/api/useStatus'
import { Button } from '@/components/ui/button'
import { AppliedControl } from '@/features/jobs/AppliedControl'
import { SetupChecklist } from '@/features/home/HomePage'
import { setupIsDone } from '@/features/home/setup'
import { DuplicatesPanel } from './DuplicatesPanel'
import { SearchPanel } from './SearchPanel'
import {
  type JobCard,
  type JobFilters,
  NO_FILTERS,
  formatDate,
  isNotChecked,
  reasonOf,
  sourceLabel,
  useJobs,
  useRecheck,
} from './api'

const input = 'rounded-md border border-muted-foreground bg-background px-3 py-1.5 text-sm'

export function JobCardItem({ job, showCheck = true }: { job: JobCard; showCheck?: boolean }) {
  const recheck = useRecheck()
  const source = job.sources[0]
  const facts = [
    job.company_name,
    job.location_text,
    job.work_mode,
    job.posted_at ? `Posted ${formatDate(job.posted_at)}` : null,
    source ? sourceLabel(source.kind) : null,
  ].filter(Boolean)
  return (
    <li className="space-y-1 rounded-lg bg-surface p-4">
      <Link to={`/jobs/${job.id}`} className="text-base font-semibold text-link underline">
        {job.title}
      </Link>
      <p className="text-sm text-muted-small">{facts.join(' · ')}</p>
      {reasonOf(job) && <p className="text-sm">{reasonOf(job)}</p>}
      <AppliedControl id={job.id} />
      {showCheck && isNotChecked(job) && (
        <div className="flex items-center gap-3">
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
    </li>
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
          <option value="manual">Added by you</option>
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

export function ExplorePage() {
  const status = useStatus()
  const [filters, setFilters] = useState<JobFilters>(NO_FILTERS)
  const jobs = useJobs(filters)
  const setupDone = setupIsDone(status.data?.checklist)
  const items = jobs.data?.pages.flatMap((page) => page.items) ?? []
  const filtered = filters.source !== '' || filters.work_mode !== '' || filters.city !== ''

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
      <p>No jobs yet. Finish setup first.</p>
    )
  } else {
    list = (
      <>
        <ul aria-label="Jobs" className="space-y-3">
          {items.map((job) => (
            <JobCardItem key={job.id} job={job} />
          ))}
        </ul>
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
      <h1 className="text-2xl font-semibold">Jobs</h1>
      {status.data && !setupDone && <SetupChecklist showAllSet={false} />}
      {setupDone && <SearchPanel />}
      {setupDone && <DuplicatesPanel />}
      <Filters value={filters} onChange={setFilters} />
      {list}
    </section>
  )
}
