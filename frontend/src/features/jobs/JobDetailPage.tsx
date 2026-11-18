import { useParams } from 'react-router'
import { BackButton } from '@/components/BackButton'
import { formatDate, useJob } from '@/features/explore/api'
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
  const facts = [
    data.company_name,
    data.location_text,
    data.work_mode,
    data.posted_at ? `Posted ${formatDate(data.posted_at)}` : null,
  ].filter(Boolean)

  return (
    <section className="space-y-4">
      <LeaveGuard when={registry.any} />
      <BackButton fallback="/explore" />
      <h1 className="text-2xl font-semibold">{data.title}</h1>
      <p className="text-muted-small">{facts.join(' · ')}</p>
      <JobDetails id={id} registry={registry} />
    </section>
  )
}
