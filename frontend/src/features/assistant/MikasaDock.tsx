import { MessageCircle, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { cn } from '@/lib/utils'
import { MikasaPanel } from './MikasaPanel'

/**
 * The round button at the bottom right of every page, and the chat popup it opens (FR-001).
 * Ctrl+/ (or Cmd+/) toggles it; Escape closes it.
 */
export function MikasaDock() {
  const [open, setOpen] = useState(false)
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === '/' && (event.ctrlKey || event.metaKey)) {
        event.preventDefault()
        setOpen((was) => !was)
      } else if (event.key === 'Escape') {
        setOpen(false)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])
  const toggle = () => setOpen((was) => !was)
  return (
    <>
      {open && <MikasaPanel onClose={() => setOpen(false)} />}
      <button
        type="button"
        aria-label="Mikasa"
        aria-expanded={open}
        aria-haspopup="dialog"
        aria-keyshortcuts="Control+/"
        title="Ask Mikasa (Ctrl+/)"
        onClick={toggle}
        className={cn(
          'fixed bottom-5 right-5 z-50 grid size-14 place-items-center rounded-full outline-none',
          'bg-primary text-primary-foreground shadow-[var(--ht-shadow-overlay)]',
          'transition-transform duration-200 hover:scale-110 focus-visible:ring-2 focus-visible:ring-ring active:scale-95',
        )}
      >
        <span
          aria-hidden
          className={cn(
            'absolute transition-[transform,opacity] duration-[var(--ht-dur-enter)]',
            open ? 'rotate-90 scale-0 opacity-0' : 'rotate-0 scale-100 opacity-100',
          )}
        >
          <MessageCircle className="size-6" />
        </span>
        <span
          aria-hidden
          className={cn(
            'absolute transition-[transform,opacity] duration-[var(--ht-dur-enter)]',
            open ? 'rotate-0 scale-100 opacity-100' : '-rotate-90 scale-0 opacity-0',
          )}
        >
          <X className="size-6" />
        </span>
      </button>
    </>
  )
}
