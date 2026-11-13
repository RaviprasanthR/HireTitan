import { Fragment, useState } from 'react'
import { Link } from 'react-router'
import { ChevronRight, Pencil } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { ReviewNotice } from '@/features/home/ReviewNotice'
import { InterviewPanel } from '@/features/jobs/interview/InterviewPanel'
import { LeaveGuard } from '@/features/jobs/interview/LeaveGuard'
import { roundStatus } from '@/features/jobs/interview/roundStatus'
import { useUnsavedRegistry, type UnsavedRegistry } from '@/features/jobs/interview/unsaved'
import { HomeTabs } from './HomeTabs'
import { formatDay, sourceLabel, usePipelineJobs, useJob, type JobCard } from './api'

type Tone = 'green' | 'yellow' | 'orange' | 'red' | 'blue' | 'purple' | 'teal' | 'grey'

/** A coloured tag. Colour never carries the meaning alone: the words are always shown. */
function Pill({ tone, children }: { tone: Tone; children: React.ReactNode }) {
  return <span className={`ht-pill ht-pill-${tone}`}>{children}</span>
}

const STATUS_TONE: Record<string, Tone> = {
  Applied: 'green',
  Inquired: 'blue',
}

const SOURCE_TONE: Record<string, Tone> = {
  naukri: 'blue',
  linkedin: 'teal',
  indeed: 'purple',
  'company job board': 'green',
  'careers page': 'orange',
  'added by you': 'yellow',
  'email alert': 'purple',
  'job site': 'blue',
}

const COLUMNS = ['Company', 'Role', 'Date', 'Status', 'Source'] as const

/** What is known about the job when the row is opened: description, places, where it came from. */
function Details({
  id,
  colSpan,
  registry,
}: {
  id: string
  colSpan: number
  registry: UnsavedRegistry
}) {
  const job = useJob(id)
  let content
  if (job.isPending) content = <p>Loading…</p>
  else if (job.isError) content = <p role="alert">Could not load this job.</p>
  else {
    const place = [job.data.location_text, job.data.work_mode].filter(Boolean).join(' · ')
    content = (
      <div className="space-y-2 text-sm">
        {place && <p className="text-muted-small">{place}</p>}
        <p className="whitespace-pre-wrap">{job.data.description}</p>
        <ul aria-label="Where it was found" className="list-disc pl-5">
          {job.data.sources.map((source) => (
            <li key={`${source.kind}-${source.url}`}>
              {sourceLabel(source.kind)}:{' '}
              <a
                href={source.url}
                target="_blank"
                rel="noreferrer noopener"
                className="text-link underline"
              >
                {source.url}
              </a>
            </li>
          ))}
        </ul>
        <Link to={`/jobs/${id}`} className="text-link underline">
          Open the full job page
        </Link>
        <InterviewPanel jobId={id} scope={id} registry={registry} />
      </div>
    )
  }
  return (
    <tr>
      <td colSpan={colSpan} className="bg-surface px-4 py-3">
        {content}
      </td>
    </tr>
  )
}

function Row({ job, registry }: { job: JobCard; registry: UnsavedRegistry }) {
  const [open, setOpen] = useState(false)
  const [asking, setAsking] = useState(false)
  const source = job.sources[0]
  // the latest round when there is one (a failed round wins), else Applied or Inquired (FR-007)
  const status = job.interview
    ? roundStatus(job.interview.state as 'scheduled' | 'cleared' | 'failed', job.interview.round)
    : job.state === 'inquired'
      ? { label: 'Inquired', tone: STATUS_TONE.Inquired }
      : { label: 'Applied', tone: STATUS_TONE.Applied }
  return (
    <Fragment>
      <tr className="ht-row border-t border-divider align-top">
        <td className="px-3 py-2">{job.company_name}</td>
        <td className="px-3 py-2">
          <Link
            to={`/jobs/${job.id}`}
            title={job.title}
            className="block max-w-[18rem] truncate font-semibold text-link underline"
          >
            {job.role}
          </Link>
        </td>
        <td className="px-3 py-2">{formatDay(job.applied_on ?? job.inquired_on)}</td>
        <td className="px-3 py-2">
          <Pill tone={status.tone ?? 'grey'}>{status.label}</Pill>
        </td>
        <td className="px-3 py-2">
          {source ? (
            <Pill tone={SOURCE_TONE[sourceLabel(source.kind).toLowerCase()] ?? 'grey'}>
              {sourceLabel(source.kind)}
            </Pill>
          ) : (
            '—'
          )}
        </td>
        <td className="px-3 py-2">
          <div className="flex gap-1">
            <button
              type="button"
              className="ht-icon-button"
              aria-expanded={open}
              aria-label={`Details for ${job.title}`}
              title={open ? 'Hide details' : 'Show details'}
              onClick={() => {
                // closing a row that holds unsaved edits asks first (FR-013)
                if (open && registry.anyIn(job.id)) setAsking(true)
                else setOpen(!open)
              }}
            >
              <ChevronRight
                aria-hidden
                className={`size-4 transition-transform ${open ? 'rotate-90' : ''}`}
              />
            </button>
            <Link
              to={`/jobs/${job.id}`}
              className="ht-icon-button"
              aria-label={`Edit ${job.title}`}
              title="Edit (change the date or undo)"
            >
              <Pencil aria-hidden className="size-4" />
            </Link>
          </div>
        </td>
      </tr>
      {open && asking && (
        <tr>
          <td colSpan={COLUMNS.length + 1} className="bg-surface px-4 py-3">
            <div role="alertdialog" aria-label="Unsaved changes" className="space-y-2">
              <p className="text-sm">You have changes that are not saved. Close the details and lose them?</p>
              <div className="flex gap-2">
                <Button
                  type="button"
                  size="sm"
                  onClick={() => {
                    setAsking(false)
                    setOpen(false)
                  }}
                >
                  Close and lose them
                </Button>
                <Button type="button" variant="ghost" size="sm" onClick={() => setAsking(false)}>
                  Keep editing
                </Button>
              </div>
            </div>
          </td>
        </tr>
      )}
      {open && <Details id={job.id} colSpan={COLUMNS.length + 1} registry={registry} />}
    </Fragment>
  )
}

/** Every job marked as applied or inquired, newest first, as a table whose rows open up. */
export function PipelinePage() {
  const jobs = usePipelineJobs()
  const registry = useUnsavedRegistry()
  const items = jobs.data?.pages.flatMap((page) => page.items) ?? []

  let body
  if (jobs.isPending) body = <p>Loading…</p>
  else if (jobs.isError) body = <p role="alert">Could not load your pipeline.</p>
  else if (items.length === 0)
    body = <p>Nothing in your pipeline yet. Mark a job as applied or inquired in Explore.</p>
  else
    body = (
      <>
        <div className="overflow-x-auto rounded-lg bg-surface">
          <table aria-label="Pipeline jobs" className="w-full text-left text-sm">
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
                <Row key={job.id} job={job} registry={registry} />
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

  return (
    <section className="space-y-4">
      <h1 className="text-2xl font-semibold">Jobs</h1>
      <ReviewNotice />
      <LeaveGuard when={registry.any} />
      <HomeTabs />
      {body}
    </section>
  )
}
