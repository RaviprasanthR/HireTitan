import { useQuery } from '@tanstack/react-query'
import { BackButton } from '@/components/BackButton'
import { Link, useParams } from 'react-router'
import { apiFetch } from '@/api/client'
import type { components } from '@/api/schema'
import { ProfileSummary } from './ProfileSummary'

type Detail = components['schemas']['VersionDetailOut']

export function VersionView() {
  const { versionId } = useParams()
  const query = useQuery({
    queryKey: ['profile', 'versions', versionId],
    queryFn: () => apiFetch<Detail>(`/profile/versions/${versionId}`),
    enabled: Boolean(versionId),
  })
  if (query.isPending) return <p>Loading this version…</p>
  if (query.isError) return <p role="alert">Could not load this version.</p>
  const v = query.data

  return (
    <article className="max-w-2xl space-y-6">
      <BackButton fallback="/profile/versions" />
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold">Version {v.number}</h1>
        <p className="text-sm text-muted-small">
          {v.is_current ? 'This is your current profile. ' : ''}
          {v.source_deleted ? 'The source file was deleted; the profile is kept. ' : ''}
          {v.source_file_name ? `Made from ${v.source_file_name}. ` : ''}
          Versions cannot be changed.{' '}
          <Link to="/profile/versions" className="text-link underline">
            All versions
          </Link>
        </p>
      </header>
      <ProfileSummary content={v.content} />
    </article>
  )
}
