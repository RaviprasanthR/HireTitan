import type { LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'

/**
 * One distinct block of a job's details, in the same card style as the other pages: a coloured
 * left edge, a small uppercase heading with an icon and an optional one-line hint. ``tone`` is one
 * of the `ht-section-*` classes in theme.css.
 */
export function Section({
  title,
  hint,
  icon: Icon,
  tone,
  as: Heading = 'h3',
  label,
  children,
}: {
  title: string
  hint?: string
  icon?: LucideIcon
  tone: string
  as?: 'h2' | 'h3'
  label?: string
  children: ReactNode
}) {
  return (
    <section aria-label={label} className={`ht-detail-card ${tone} space-y-3`}>
      <div>
        <Heading className="ht-detail-heading !mb-0">
          {Icon && <Icon aria-hidden className="size-4" />}
          {title}
        </Heading>
        {hint && <p className="mt-1 text-sm text-muted-small">{hint}</p>}
      </div>
      {children}
    </section>
  )
}
