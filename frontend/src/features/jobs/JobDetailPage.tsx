import { Link, useParams } from 'react-router'
import { Button } from '@/components/ui/button'
import { formatDate, isNotChecked, sourceLabel, useJob, useRecheck } from '@/features/explore/api'

type Flag = { rule_id: string; severity: string; excerpt: string; location: string }

function InjectionWarning({ flags }: { flags: Flag[] }) {
  if (flags.length === 0) return null
  return (
    <div role="alert" className="space-y-1 rounded-lg border border-warning p-3 text-sm">
      <p className="font-medium text-warning">
        This posting contains text that looks like instructions to an AI.
      </p>
      <p>It was treated as plain text and did not change any decision. Be careful with it.</p>
      <ul className="list-disc pl-5">
        {flags.map((flag) => (
          <li key={`${flag.rule_id}:${flag.excerpt}`}>
            “{flag.excerpt}” ({flag.location})
          </li>
        ))}
      </ul>
    </div>
  )
}

function safeLink(url: string | null | undefined): string | null {
  return url && /^https?:\/\//i.test(url) ? url : null
}

/** One job in full: description, where it was found, why it is listed, and what to be careful of. */
export function JobDetailPage() {
  const { id = '' } = useParams()
  const job = useJob(id)
  const recheck = useRecheck()
  if (job.isPending) return <p>Loading…</p>
  if (job.isError) return <p role="alert">Could not load this job.</p>
  const data = job.data
  const original = safeLink(data.canonical_url) ?? safeLink(data.sources[0]?.url)
  const facts = [
    data.company_name,
    data.location_text,
    data.work_mode,
    data.posted_at ? `Posted ${formatDate(data.posted_at)}` : null,
  ].filter(Boolean)

  return (
    <section className="space-y-4">
      <h1 className="text-2xl font-semibold">{data.title}</h1>
      <p className="text-muted-small">{facts.join(' · ')}</p>
      <InjectionWarning flags={data.injection_flags as Flag[]} />

      {data.decision && (
        <div className="space-y-2 rounded-lg bg-surface p-4">
          <p className="font-medium">Why it is listed</p>
          <p>{data.decision.reason}</p>
          {isNotChecked(data) && (
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
                <span className="text-sm text-danger">{recheck.error.message}</span>
              )}
            </div>
          )}
        </div>
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

      <section className="space-y-2">
        <h2 className="text-lg font-semibold">Description</h2>
        <p className="whitespace-pre-wrap">{data.description}</p>
      </section>

      <section className="space-y-2">
        <h2 className="text-lg font-semibold">Sources</h2>
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
        <h2 className="text-lg font-semibold">Decision history</h2>
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
    </section>
  )
}
