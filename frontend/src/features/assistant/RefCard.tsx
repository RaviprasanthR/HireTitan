import { Link } from 'react-router'
import { useRefCard } from './api'

/**
 * An item Mikasa named, as the person sees it (research R5). Private details (a contact's name,
 * an interview's feedback) are fetched here, in the browser; the model only ever had the ref.
 */
export function RefCard({ refText }: { refText: string }) {
  const card = useRefCard(refText)
  if (card.isPending) {
    return (
      <span className="my-1 block rounded-md border border-divider px-2 py-1 text-xs text-muted-small">
        Loading…
      </span>
    )
  }
  if (card.isError || !card.data) {
    return (
      <span className="my-1 block rounded-md border border-divider px-2 py-1 text-xs text-muted-small">
        This item no longer exists.
      </span>
    )
  }
  const { title, subtitle, lines, link } = card.data
  const body = (
    <>
      <span className="block font-medium">{title}</span>
      {subtitle && <span className="block text-xs text-muted-small">{subtitle}</span>}
      {lines?.map((line, index) => (
        <span key={index} className="block whitespace-pre-wrap text-xs">
          {line}
        </span>
      ))}
    </>
  )
  return link ? (
    <Link
      to={link}
      data-testid="ref-card"
      className="my-1 block rounded-md border border-divider bg-background px-2 py-1 text-sm hover:border-primary"
    >
      {body}
    </Link>
  ) : (
    <span
      data-testid="ref-card"
      className="my-1 block rounded-md border border-divider bg-background px-2 py-1 text-sm"
    >
      {body}
    </span>
  )
}
