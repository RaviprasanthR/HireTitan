import type { components } from '@/api/schema'

type Content = components['schemas']['ProfileContentModel']

const ym = (v: { year: number; month?: number | null } | null | undefined) =>
  v ? (v.month ? `${v.year}-${String(v.month).padStart(2, '0')}` : String(v.year)) : ''

/** A profile's content to read: contact, headline, summary, experience, education and skills.
 * Shown for the current profile on the Profile page (R10) and for any saved version. */
export function ProfileSummary({ content: c }: { content: Content }) {
  return (
    <>
      <section className="space-y-1">
        <h2 className="text-lg font-semibold">Contact</h2>
        <p>{c.contact.name}</p>
        {c.contact.email && <p>{c.contact.email}</p>}
        {c.contact.phone && <p>{c.contact.phone}</p>}
        {c.contact.location && <p>{c.contact.location}</p>}
      </section>
      {c.headline && <p className="text-lg">{c.headline}</p>}
      {c.summary && <p className="max-w-[50ch]">{c.summary}</p>}
      {(c.experience ?? []).length > 0 && (
        <section className="space-y-3">
          <h2 className="text-lg font-semibold">Experience</h2>
          {c.experience?.map((e, i) => (
            <div key={e.id ?? i}>
              <p className="font-medium">{e.employer}</p>
              <p>{e.title}</p>
              <p className="ht-figure text-sm text-muted-small">
                {[ym(e.start), e.current ? 'Present' : ym(e.end)].filter(Boolean).join(' to ')}
              </p>
              <ul className="list-disc pl-5">
                {e.bullets?.map((b, j) => (
                  <li key={j} className="max-w-[50ch]">{b}</li>
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
    </>
  )
}
