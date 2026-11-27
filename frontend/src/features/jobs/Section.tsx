import type { LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'

/**
 * One distinct block of a job's details in the neutral card style of every page (no per-section
 * accent, FR-005): a heading with an icon and an optional one-line hint.
 */
export function Section({
  title,
  hint,
  icon: Icon,
  as: Heading = 'h3',
  label,
  children,
}: {
  title: string
  hint?: string
  icon?: LucideIcon
  as?: 'h2' | 'h3'
  label?: string
  children: ReactNode
}) {
  return (
    <section aria-label={label} className="ht-detail-card space-y-3">
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
