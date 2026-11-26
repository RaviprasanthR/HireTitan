import { X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { MikasaAvatar } from './MikasaAvatar'
import { MikasaPanel } from './MikasaPanel'

/** How long after a page opens Mikasa asks if you need help, once per visit (sessionStorage). */
export const GREETING_DELAY_MS = 4000
const GREETED = 'ht-mikasa-greeted'

/**
 * The round button at the bottom right of every page, and the chat popup it opens (FR-001).
 * Ctrl+/ (or Cmd+/) toggles it; Escape closes it.
 */
export function MikasaDock() {
  const [open, setOpen] = useState(false)
  const [greeting, setGreeting] = useState(false)
  // a short offer of help, never stealing the focus; once answered (or the chat opened) it stays
  // away for the rest of the visit
  useEffect(() => {
    if (sessionStorage.getItem(GREETED)) return
    const timer = window.setTimeout(() => {
      if (!sessionStorage.getItem(GREETED)) setGreeting(true)
    }, GREETING_DELAY_MS)
    return () => window.clearTimeout(timer)
  }, [])
  useEffect(() => {
    if (open) sessionStorage.setItem(GREETED, '1')
  }, [open])
  const dismiss = () => {
    sessionStorage.setItem(GREETED, '1')
    setGreeting(false)
  }
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
      {greeting && !open && (
        <div
          role="status"
          aria-label="Mikasa says"
          className="mikasa-pop fixed right-4 bottom-[calc(var(--ht-bottom-bar)+5rem)] z-50 w-64 space-y-3 rounded-2xl rounded-br-md bg-surface p-4 text-sm shadow-[var(--ht-shadow-overlay)] md:right-5 md:bottom-24"
        >
          <p>Hi, I’m Mikasa. Need a hand with your job search?</p>
          <div className="flex gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => {
                dismiss()
                setOpen(true)
              }}
            >
              Yes, help me
            </Button>
            <Button type="button" variant="ghost" size="sm" onClick={dismiss}>
              Not now
            </Button>
          </div>
        </div>
      )}
      <button
        type="button"
        aria-label="Mikasa"
        aria-expanded={open}
        aria-haspopup="dialog"
        aria-keyshortcuts="Control+/"
        title="Ask Mikasa (Ctrl+/)"
        onClick={toggle}
        className={cn(
          'ht-mikasa-dock fixed bottom-[calc(var(--ht-bottom-bar)+0.75rem)] right-4 z-50 md:bottom-5 md:right-5 grid size-14 place-items-center rounded-full outline-none',
          // flat (DESIGN.md, Mikasa button): the hover steps the colour, the press scales to 0.96
          'ht-gradient-fill bg-primary text-primary-foreground hover:bg-[var(--ht-accent-hover)]',
          'transition-[background-color,transform] duration-[var(--ht-dur-fast)] ease-[var(--ht-ease)] focus-visible:ring-2 focus-visible:ring-ring active:scale-[0.96]',
        )}
      >
        <span
          aria-hidden
          className={cn(
            'absolute transition-[transform,opacity] duration-[var(--ht-dur-enter)]',
            open ? 'rotate-90 scale-0 opacity-0' : 'rotate-0 scale-100 opacity-100',
          )}
        >
          {/* her face floats gently and tilts on hover (still for reduced motion) */}
          <span className="ht-mikasa-float block size-14">
            <MikasaAvatar className="size-14 bg-transparent" />
          </span>
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
