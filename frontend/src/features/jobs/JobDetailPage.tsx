import { useParams } from 'react-router'
import { BackButton } from '@/components/BackButton'
import { StageChip } from '@/components/StageChip'
import { formatDate, newWorkMode, useJob } from '@/features/explore/api'
import { JobDetails } from './JobDetails'
import { LeaveGuard } from './interview/LeaveGuard'
import { useUnsavedRegistry } from './interview/unsaved'

/** One job in full: its title and facts, then everything about it (the same details an expanded
 * Explore row shows). */
export function JobDetailPage() {
  const { id = '' } = useParams()
  const job = useJob(id)
  const registry = useUnsavedRegistry()
  if (job.isPending) return <p>Loading…</p>
  if (job.isError) return <p role="alert">Could not load this job.</p>
  const data = job.data
  const location = data.location_text ?? ''
  // facts set apart by space, the work mode only when the location does not say it (FR-007)
  const facts = [
    data.company_name,
    location,
    newWorkMode(location, data.work_mode),
    data.posted_at ? `Posted ${formatDate(data.posted_at)}` : null,
  ].filter((fact): fact is string => Boolean(fact))
  const stage = data.state === 'applied' || data.state === 'inquired' ? data.state : null

  return (
    <section className="space-y-4">
      <LeaveGuard when={registry.any} />
      <BackButton fallback="/explore" />
      <header className="space-y-2">
        <h1 className="text-2xl font-semibold">{data.title}</h1>
        <p className="flex flex-wrap gap-x-4 text-muted-small">
          {facts.map((fact, i) => (
            <span key={`${i}:${fact}`}>{fact}</span>
          ))}
        </p>
        {stage && <StageChip stage={stage} />}
      </header>
      <JobDetails id={id} registry={registry} />
    </section>
  )
}
