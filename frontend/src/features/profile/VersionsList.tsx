import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router'
import { apiFetch } from '@/api/client'
import type { components } from '@/api/schema'

type Version = components['schemas']['VersionOut']

const CREATED_BY: Record<string, string> = {
  extraction: 'From a resume',
  manual: 'Typed by hand',
  manual_edit: 'Edited by hand',
}

export function VersionsList() {
  const query = useQuery({
    queryKey: ['profile', 'versions'],
    queryFn: () => apiFetch<Version[]>('/profile/versions'),
  })
  if (query.isPending) return <p>Loading your versions…</p>
  if (query.isError) return <p role="alert">Could not load your versions.</p>
  const versions = query.data

  return (
    <section className="max-w-2xl space-y-4">
      <h1 className="text-2xl font-semibold">Profile versions</h1>
      {versions.length === 0 ? (
        <p>
          No profile yet.{' '}
          <Link to="/profile" className="text-link underline">
            Add a resume
          </Link>{' '}
          or{' '}
          <Link to="/profile/edit" className="text-link underline">
            fill in by hand
          </Link>
          .
        </p>
      ) : (
        <ul className="space-y-3">
          {versions.map((v) => (
            <li key={v.id} className="flex flex-wrap items-center gap-3 rounded-lg bg-surface p-4">
              <span className="font-medium">Version {v.number}</span>
              {v.is_current && (
                <span className="rounded bg-primary px-2 py-0.5 text-xs text-primary-foreground">
                  Current
                </span>
              )}
              <span className="text-sm text-muted-small">
                {CREATED_BY[v.created_by] ?? v.created_by}
                {v.source_file_name ? ` · ${v.source_file_name}` : ''}
                {v.source_deleted ? ' · the source file was deleted' : ''}
              </span>
              <span className="text-sm text-muted-small">
                {new Date(v.created_at).toLocaleDateString('en-GB')}
              </span>
              <Link to={`/profile/versions/${v.id}`} className="ml-auto text-link underline">
                View
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
