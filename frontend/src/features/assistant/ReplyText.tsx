import { Link } from 'react-router'
import { pageName } from './pages'
import { RefCard } from './RefCard'

const TOKEN = /\[\[(page:\/[^\]\s]*|[a-z_]+:[0-9a-fA-F-]{36})\]\]/g

/**
 * Mikasa's words as plain text, with her ref and page tokens turned into cards and links.
 * Nothing in the text is ever rendered as HTML or Markdown (EC-13).
 */
export function ReplyText({ text }: { text: string }) {
  const parts: React.ReactNode[] = []
  let last = 0
  for (const match of text.matchAll(TOKEN)) {
    const index = match.index ?? 0
    if (index > last) parts.push(text.slice(last, index))
    const token = match[1] ?? ''
    if (token.startsWith('page:')) {
      const path = token.slice(5)
      parts.push(
        <Link
          key={`${index}-page`}
          to={path}
          className="text-link underline-offset-2 hover:underline"
        >
          {pageName(path)}
        </Link>,
      )
    } else {
      parts.push(<RefCard key={`${index}-${token}`} refText={token} />)
    }
    last = index + match[0].length
  }
  if (last < text.length) parts.push(text.slice(last))
  return <div className="whitespace-pre-wrap break-words">{parts}</div>
}
