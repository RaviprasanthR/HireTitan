import { Fragment, useState } from 'react'
import { PipelineChart } from './PipelineChart'
import { OverviewLayout } from '@/components/OverviewLayout'
import { Link } from 'react-router'
import {
  ArrowUpRight,
  ChevronRight,
  ExternalLink,
  FileText,
  Laptop,
  Link2,
  MapPin,
  Pencil,
  Users,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { ReviewNotice } from '@/features/home/ReviewNotice'
import { InterviewPanel } from '@/features/jobs/interview/InterviewPanel'
import { LeaveGuard } from '@/features/jobs/interview/LeaveGuard'
import { roundStatus } from '@/features/jobs/interview/roundStatus'
import { useUnsavedRegistry, type UnsavedRegistry } from '@/features/jobs/interview/unsaved'
import { EditJobDialog } from '@/features/jobs/EditJobDialog'
import { resumeName } from '@/features/jobs/resume/resumeApi'
import { HomeTabs } from './HomeTabs'
import { Pill } from './Pill'
import { SOURCE_TONE, type Tone } from './pillTones'
import { formatDay, sourceLabel, usePipelineJobs, useJob, type JobCard } from './api'

const STATUS_TONE: Record<string, Tone> = {
  Applied: 'green',
  Inquired: 'blue',
}

const COLUMNS = ['Company', 'Role', 'Date', 'Status', 'Resume', 'Source'] as const

/** What is known about the job when the row is opened: description, places, where it came from. */
function Details({ id, colSpan }: { id: string; colSpan: number }) {
  const job = useJob(id)
  let content
  if (job.isPending) content = <p>Loading…</p>
  else if (job.isError) content = <p role="alert">Could not load this job.</p>
  else {
    const { location_text: location, work_mode: mode } = job.data
    content = (
      <div className="space-y-3 text-sm">
        {(location || mode) && (
          <div className="flex flex-wrap gap-2">
            {location && (
              <span aria-label="Location" className="ht-fact">
                <MapPin aria-hidden className="size-4 text-subtle" />
                {location}
              </span>
            )}
            {mode && (
              <span aria-label="Work mode" className="ht-fact">
                <Laptop aria-hidden className="size-4 text-subtle" />
                {mode}
              </span>
            )}
          </div>
        )}

        <section className="ht-detail-card ht-detail-description">
          <h3 className="ht-detail-heading">
            <FileText aria-hidden className="size-4" />
            Description
          </h3>
          <p className="max-h-56 overflow-y-auto whitespace-pre-wrap pr-2">
            {job.data.description}
          </p>
        </section>

        <section className="ht-detail-card ht-detail-sources">
          <h3 className="ht-detail-heading">
            <Link2 aria-hidden className="size-4" />
            Where it was found
          </h3>
          <ul aria-label="Where it was found" className="space-y-1.5">
            {job.data.sources.map((source) => (
              <li
                key={`${source.kind}-${source.url}`}
                className="flex flex-wrap items-center gap-2"
              >
                <Pill tone={SOURCE_TONE[sourceLabel(source.kind).toLowerCase()] ?? 'grey'}>
                  {sourceLabel(source.kind)}
                </Pill>
                <a
                  href={source.url}
                  target="_blank"
                  rel="noreferrer noopener"
                  className="inline-flex min-w-0 items-center gap-1.5 text-link underline"
                >
                  <ExternalLink aria-hidden className="size-3.5 shrink-0" />
                  <span className="truncate">{source.url}</span>
                </a>
              </li>
            ))}
          </ul>
        </section>

        <Link to={`/jobs/${id}`} className="ht-detail-open">
          <ArrowUpRight aria-hidden className="size-4" />
          Open the full job page
        </Link>

        <section className="ht-detail-card ht-detail-interview">
          <h3 className="ht-detail-heading">
            <Users aria-hidden className="size-4" />
            Interview tracking
          </h3>
          <InterviewPanel jobId={id} readOnly />
        </section>
      </div>
    )
  }
  return (
    <tr role="row">
      <td role="cell" colSpan={colSpan} className="bg-surface px-4 py-3">
        {content}
      </td>
    </tr>
  )
}

/** The resume used: its name, cut to fit with the whole name on hover, or a dash. A removed
 *  file's name is followed by a "(removed)" marker that is never cut off. */
function ResumeCell({ resume }: { resume: JobCard['resume'] }) {
  const name = resumeName(resume)
  if (name === '') return <>—</>
  if (resume?.state !== 'removed')
    return (
      <span title={name} className="block max-w-[12rem] truncate">
        {name}
      </span>
    )
  return (
    <span title={name} className="flex max-w-[14rem] items-baseline gap-1">
      <span className="min-w-0 truncate">{resume.name}</span>{' '}
      <span className="shrink-0 text-muted-small">(removed)</span>
    </span>
  )
}

function Row({ job, registry }: { job: JobCard; registry: UnsavedRegistry }) {
  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState(false)
  const source = job.sources[0]
  // the latest round when there is one (a failed round wins), else Applied or Inquired (FR-007)
  const status = job.interview
    ? roundStatus(job.interview.state as 'scheduled' | 'cleared' | 'failed', job.interview.round)
    : job.state === 'inquired'
      ? { label: 'Inquired', tone: STATUS_TONE.Inquired }
      : { label: 'Applied', tone: STATUS_TONE.Applied }
  return (
    <Fragment>
      <tr role="row" className="ht-row border-t border-divider align-top">
        <td role="cell" className="px-3 py-2">
          {job.company_name}
        </td>
        <td role="cell" className="px-3 py-2">
          <Link
            to={`/jobs/${job.id}`}
            title={job.title}
            className="block font-semibold text-link underline md:max-w-[18rem] md:truncate"
          >
            {job.role}
          </Link>
        </td>
        <td role="cell" data-label="Date" className="px-3 py-2">
          {formatDay(job.applied_on ?? job.inquired_on)}
        </td>
        <td role="cell" data-label="Status" className="px-3 py-2">
          <Pill tone={status.tone ?? 'grey'}>{status.label}</Pill>
        </td>
        <td role="cell" data-label="Resume" className="px-3 py-2">
          <ResumeCell resume={job.resume} />
        </td>
        <td role="cell" data-label="Source" className="px-3 py-2">
          {source ? (
            <Pill tone={SOURCE_TONE[sourceLabel(source.kind).toLowerCase()] ?? 'grey'}>
              {sourceLabel(source.kind)}
            </Pill>
          ) : (
            '—'
          )}
        </td>
        <td role="cell" className="px-3 py-2">
          <div className="flex gap-1">
            <button
              type="button"
              className="ht-icon-button"
              aria-expanded={open}
              aria-label={`Details for ${job.title}`}
              title={open ? 'Hide details' : 'Show details'}
              onClick={() => setOpen(!open)}
            >
              <ChevronRight
                aria-hidden
                className={`size-4 transition-transform ${open ? 'rotate-90' : ''}`}
              />
            </button>
            <button
              type="button"
              className="ht-icon-button"
              aria-label={`Edit ${job.title}`}
              title="Edit (change the date, undo, or record the interviews)"
              onClick={() => setEditing(true)}
            >
              <Pencil aria-hidden className="size-4" />
            </button>
          </div>
        </td>
      </tr>
      {editing && (
        <EditJobDialog
          jobId={job.id}
          title={job.title}
          registry={registry}
          colSpan={COLUMNS.length + 1}
          onClose={() => setEditing(false)}
        />
      )}
      {open && <Details id={job.id} colSpan={COLUMNS.length + 1} />}
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
        <div className="ht-table-scroll overflow-x-auto md:rounded-lg md:bg-surface">
          <table
            role="table"
            aria-label="Pipeline jobs"
            className="ht-table-cards w-full text-left text-sm"
          >
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
    <section className="ht-fit-page space-y-4">
      <h1 className="text-2xl font-semibold">Jobs</h1>
      <ReviewNotice />
      <LeaveGuard when={registry.any} />
      <HomeTabs />
      <OverviewLayout label="Pipeline overview" overview={<PipelineChart />}>
        {body}
      </OverviewLayout>
    </section>
  )
}
