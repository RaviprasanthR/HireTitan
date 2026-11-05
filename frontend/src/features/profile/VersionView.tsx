import { useQuery } from '@tanstack/react-query'
import { Link, useParams } from 'react-router'
import { apiFetch } from '@/api/client'
import type { components } from '@/api/schema'

type Detail = components['schemas']['VersionDetailOut']

const ym = (v: { year: number; month?: number | null } | null | undefined) =>
  v ? (v.month ? `${v.year}-${String(v.month).padStart(2, '0')}` : String(v.year)) : ''

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
  const c = v.content

  return (
    <article className="max-w-2xl space-y-6">
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
      <section className="space-y-1">
        <h2 className="text-lg font-semibold">Contact</h2>
        <p>{c.contact.name}</p>
        {c.contact.email && <p>{c.contact.email}</p>}
        {c.contact.phone && <p>{c.contact.phone}</p>}
        {c.contact.location && <p>{c.contact.location}</p>}
      </section>
      {c.headline && <p className="text-lg">{c.headline}</p>}
      {c.summary && <p>{c.summary}</p>}
      {(c.experience ?? []).length > 0 && (
        <section className="space-y-3">
          <h2 className="text-lg font-semibold">Experience</h2>
          {c.experience?.map((e, i) => (
            <div key={e.id ?? i}>
              <p className="font-medium">{e.employer}</p>
              <p>{e.title}</p>
              <p className="text-sm text-muted-small">
                {ym(e.start)} – {e.current ? 'Present' : ym(e.end)}
              </p>
              <ul className="list-disc pl-5">
                {e.bullets?.map((b, j) => (
                  <li key={j}>{b}</li>
                ))}
              </ul>
            </div>
          ))}
        </section>
      )}
      {(c.education ?? []).length > 0 && (
        <section className="space-y-2">
          <h2 className="text-lg font-semibold">Education</h2>
          {c.education?.map((e, i) => (
            <p key={e.id ?? i}>
              {e.institution}
              {e.qualification ? `, ${e.qualification}` : ''}
            </p>
          ))}
        </section>
      )}
      {(c.skills ?? []).length > 0 && (
        <section className="space-y-2">
          <h2 className="text-lg font-semibold">Skills</h2>
          <ul className="flex flex-wrap gap-2">
            {c.skills?.map((s) => (
              <li key={s} className="rounded bg-surface px-2 py-1 text-sm">
                {s}
              </li>
            ))}
          </ul>
        </section>
      )}
    </article>
  )
}
