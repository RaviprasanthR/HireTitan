import { Check, Copy, Loader2 } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router'
import { useRefCard } from './api'

/**
 * An item Mikasa named, as the person sees it (research R5). Private details (a contact's name,
 * an interview's feedback) are fetched here, in the browser; the model only ever had the ref.
 */
function CopyDraft({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <button
      type="button"
      className="mt-1 inline-flex items-center gap-1 rounded-md border border-white/10 px-2 py-0.5 text-xs hover:border-primary"
      onClick={() => {
        void navigator.clipboard?.writeText(text).then(() => {
          setCopied(true)
          setTimeout(() => setCopied(false), 2000)
        })
      }}
    >
      {copied ? <Check aria-hidden className="size-3" /> : <Copy aria-hidden className="size-3" />}
      {copied ? 'Copied' : 'Copy'}
    </button>
  )
}

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
  if (card.data.kind === 'draft') {
    const writing = subtitle?.includes('writing') ?? false
    const text = lines?.join('\n\n')
    return (
      <div
        data-testid="ref-card"
        className="mikasa-rise my-1 rounded-xl border border-white/10 bg-background px-3 py-2 text-sm"
      >
        <span className="block font-medium">{title}</span>
        {subtitle && (
          <span className="flex items-center gap-1 text-xs text-muted-small">
            {writing && <Loader2 aria-hidden className="size-3 animate-spin" />}
            {subtitle}
          </span>
        )}
        {text && <span className="mt-1 block whitespace-pre-wrap text-xs">{text}</span>}
        <span className="mt-1 flex items-center gap-3">
          {text && <CopyDraft text={text} />}
          {link && (
            <Link to={link} className="text-xs text-link">
              Open the job
            </Link>
          )}
        </span>
      </div>
    )
  }
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
