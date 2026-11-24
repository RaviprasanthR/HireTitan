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
  const [everOpened, setEverOpened] = useState(false) // the attention ring stops after the first open
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
  const toggle = () => {
    setOpen((was) => !was)
    setEverOpened(true)
  }
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
          'bg-gradient-to-br from-primary to-[#a99ce6] text-primary-foreground shadow-lg shadow-black/40',
          'transition-transform duration-200 hover:scale-110 focus-visible:ring-2 focus-visible:ring-ring active:scale-95',
          !open && !everOpened && 'mikasa-ring',
        )}
      >
        <span
          aria-hidden
          className={cn(
            'absolute transition-all duration-200',
            open ? 'rotate-90 scale-0 opacity-0' : 'rotate-0 scale-100 opacity-100',
          )}
        >
          <MessageCircle className="size-6" />
        </span>
        <span
          aria-hidden
          className={cn(
            'absolute transition-all duration-200',
            open ? 'rotate-0 scale-100 opacity-100' : '-rotate-90 scale-0 opacity-0',
          )}
        >
          <X className="size-6" />
        </span>
      </button>
    </>
  )
}
