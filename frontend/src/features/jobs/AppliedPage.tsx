import { Fragment, useState } from 'react'
import { Link } from 'react-router'
import { ChevronRight, Pencil } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { formatDay, sourceLabel, useAppliedJobs, useJob, type JobCard } from '@/features/explore/api'

type Tone = 'green' | 'yellow' | 'orange' | 'red' | 'blue' | 'purple' | 'teal' | 'grey'

/** A coloured tag. Colour never carries the meaning alone: the words are always shown. */
function Pill({ tone, children }: { tone: Tone; children: React.ReactNode }) {
  return <span className={`ht-pill ht-pill-${tone}`}>{children}</span>
}

const STATUS_TONE: Record<string, Tone> = {
  Applied: 'green',
  'In review': 'yellow',
  Interview: 'orange',
  Rejected: 'red',
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

const COLUMNS = ['Company', 'Role', 'Applied on', 'Status', 'Source'] as const

/** What is known about the job when the row is opened: description, places, where it came from. */
function Details({ id, colSpan }: { id: string; colSpan: number }) {
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
              <a href={source.url} target="_blank" rel="noreferrer noopener" className="text-link underline">
                {source.url}
              </a>
            </li>
          ))}
        </ul>
        <Link to={`/jobs/${id}`} className="text-link underline">
          Open the full job page
        </Link>
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

function Row({ job }: { job: JobCard }) {
  const [open, setOpen] = useState(false)
  const source = job.sources[0]
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
        <td className="px-3 py-2">{formatDay(job.applied_on)}</td>
        <td className="px-3 py-2">
          <Pill tone={STATUS_TONE.Applied ?? 'green'}>Applied</Pill>
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
              onClick={() => setOpen(!open)}
            >
              <ChevronRight aria-hidden className={`size-4 transition-transform ${open ? 'rotate-90' : ''}`} />
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
      {open && <Details id={job.id} colSpan={COLUMNS.length + 1} />}
    </Fragment>
  )
}

/** Every job marked as applied, newest application first, as a table whose rows open up. */
export function AppliedPage() {
  const jobs = useAppliedJobs()
  const items = jobs.data?.pages.flatMap((page) => page.items) ?? []

  let body
  if (jobs.isPending) body = <p>Loading…</p>
  else if (jobs.isError) body = <p role="alert">Could not load your applied jobs.</p>
  else if (items.length === 0) body = <p>You haven’t marked any job as applied yet.</p>
  else
    body = (
      <>
        <div className="overflow-x-auto rounded-lg bg-surface">
          <table aria-label="Applied jobs" className="w-full text-left text-sm">
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
                <Row key={job.id} job={job} />
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
      <h1 className="text-2xl font-semibold">Applied</h1>
      {body}
    </section>
  )
}
