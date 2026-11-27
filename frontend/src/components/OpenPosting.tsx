import { safeHttpUrl } from '@/lib/safeUrl'
import { ExternalLink } from 'lucide-react'

/**
 * A link to the job's original posting, which opens in a new tab and says so (FR-020). `title`
 * names the job when several of these sit in one list; `iconOnly` shows just the icon. The spoken
 * name starts with the visible words (WCAG 2.5.3).
 */
export function OpenPosting({
  href,
  title,
  iconOnly = false,
}: {
  href: string
  title?: string
  iconOnly?: boolean
}) {
  const name = title ? `Open posting for ${title}` : 'Open posting'
  return (
    <a
      href={safeHttpUrl(href)}
      target="_blank"
      rel="noreferrer noopener"
      aria-label={`${name} (opens in a new tab)`}
      title={iconOnly ? name : undefined}
      className={
        iconOnly
          ? 'ht-icon-button'
          : 'inline-flex items-center gap-1.5 text-link underline underline-offset-2'
      }
    >
      {!iconOnly && 'Open posting'}
      <ExternalLink aria-hidden className="size-4" />
    </a>
  )
}
