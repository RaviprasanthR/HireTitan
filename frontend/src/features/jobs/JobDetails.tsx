import { Link } from 'react-router'
import { Button } from '@/components/ui/button'
import { CompanyPanel } from '@/features/companies/CompanyPanel'
import {
  formatDate,
  formatDay,
  isNotChecked,
  sourceLabel,
  useJob,
  useRecheck,
} from '@/features/explore/api'
import { InjectionWarning, type InjectionFlag } from './InjectionWarning'
import { InterviewPanel } from './interview/InterviewPanel'
import { type UnsavedRegistry, useUnsavedRegistry } from './interview/unsaved'
import { PipelineControl } from './PipelineControl'
import { useUndoPipeline } from './pipelineApi'

function safeLink(url: string | null | undefined): string | null {
  return url && /^https?:\/\//i.test(url) ? url : null
}

/**
 * Everything about one job below its title: why it is listed, what to be careful of, the
 * description, where it was found and how it was decided. The job page and an expanded Explore row
 * show the same thing. ``actions`` is off where the surrounding row already has the buttons.
 */
export function JobDetails({
  id,
  registry,
  actions = true,
}: {
  id: string
  registry?: UnsavedRegistry
  actions?: boolean
}) {
  const job = useJob(id)
  const recheck = useRecheck()
  const undoApplied = useUndoPipeline('applied')
  const undoInquired = useUndoPipeline('inquired')
  const ownRegistry = useUnsavedRegistry()
  const unsaved = registry ?? ownRegistry
  if (job.isPending) return <p role="status">Loading…</p>
  if (job.isError) return <p role="alert">Could not load this job.</p>
  const data = job.data
  const Heading = actions ? 'h2' : 'h3' // in an Explore row the sections sit below the list, not beside the page's own
  const original = safeLink(data.canonical_url) ?? safeLink(data.sources[0]?.url)

  return (
    <div role="group" aria-label={`Details of ${data.title}`} className="space-y-4">
      <InjectionWarning flags={data.injection_flags as InjectionFlag[]} />

      {data.decision && (
        <div className="space-y-2 rounded-lg bg-surface p-4">
          <p className="font-medium">Why it is listed</p>
          <p>{data.decision.reason}</p>
          {actions && isNotChecked(data) && (
            <div className="flex items-center gap-3">
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={recheck.isPending || recheck.isSuccess}
                onClick={() => recheck.mutate(data.id)}
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
        </div>
      )}

      {data.state === 'applied' || data.state === 'inquired' ? (
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <span>
            {data.state === 'applied'
              ? `Applied on ${formatDay(data.applied_on)}`
              : `Inquired on ${formatDay(data.inquired_on)}`}
          </span>
          {actions && (
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={undoApplied.isPending || undoInquired.isPending}
              onClick={() =>
                (data.state === 'applied' ? undoApplied : undoInquired).mutate(data.id)
              }
            >
              Undo
            </Button>
          )}
          {actions && data.state === 'inquired' && (
            <PipelineControl
              id={data.id}
              state={data.state}
              ownResumeId={
                data.resume === undefined ? undefined : (data.resume.resume_file_id ?? null)
              }
              ownRemoved={data.resume?.state === 'removed'}
            />
          )}
        </div>
      ) : (
        actions && data.state !== 'deleted' && <PipelineControl id={data.id} state={data.state} />
      )}

      {data.state !== 'deleted' && (
        <InterviewPanel
          key={data.id}
          jobId={data.id}
          heading="Interview details"
          registry={unsaved}
          hideWhenEmpty={data.state !== 'applied' && data.state !== 'inquired'}
          // in a list row the details are for reading: editing them happens on the job page, where
          // leaving with unsaved edits is asked about
          readOnly={!actions}
        />
      )}

      <div className="flex flex-wrap items-center gap-4 text-sm">
        {original && (
          <a
            href={original}
            target="_blank"
            rel="noreferrer noopener"
            className="text-link underline"
          >
            Open original posting
          </a>
        )}
        {data.first_search_id && (
          <Link to={`/search/runs/${data.first_search_id}`} className="text-link underline">
            First found in this search
          </Link>
        )}
      </div>

      {data.company_id && (
        <section className="space-y-2">
          <Heading className="text-lg font-semibold">People at {data.company_name}</Heading>
          <CompanyPanel companyId={data.company_id} companyName={data.company_name} />
        </section>
      )}

      <section className="space-y-2">
        <Heading className="text-lg font-semibold">Description</Heading>
        <p className="whitespace-pre-wrap">{data.description}</p>
      </section>

      <section className="space-y-2">
        <Heading className="text-lg font-semibold">Sources</Heading>
        <ul aria-label="Sources" className="space-y-1 text-sm">
          {data.sources.map((source) => {
            const href = safeLink(source.url)
            return (
              <li key={`${source.kind}:${source.url}`}>
                {sourceLabel(source.kind)}:{' '}
                {href ? (
                  <a
                    href={href}
                    target="_blank"
                    rel="noreferrer noopener"
                    className="text-link underline"
                  >
                    {source.url}
                  </a>
                ) : (
                  source.url
                )}
              </li>
            )
          })}
        </ul>
      </section>

      <section className="space-y-2">
        <Heading className="text-lg font-semibold">Decision history</Heading>
        <ul aria-label="Decision history" className="space-y-1 text-sm">
          {data.decision_history.map((decision) => (
            <li key={`${decision.created_at}:${decision.decided_by}`}>
              {formatDate(decision.created_at)} ·{' '}
              {decision.outcome === 'shown' ? 'Kept' : 'Left out'} by{' '}
              {decision.decided_by === 'ai'
                ? 'the AI'
                : decision.decided_by === 'rule'
                  ? 'your rules'
                  : decision.decided_by === 'person'
                    ? 'you'
                    : 'rules only (not checked by AI)'}
              : {decision.reason}
              {decision.is_current && ' (current)'}
            </li>
          ))}
        </ul>
      </section>
    </div>
  )
}
