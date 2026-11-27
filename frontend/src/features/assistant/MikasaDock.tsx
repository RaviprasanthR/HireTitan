import { X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { cn } from '@/lib/utils'
import { TypingDots } from './TypingDots'
import { MikasaAvatar } from './MikasaAvatar'
import { MikasaPanel } from './MikasaPanel'

/** How long after a page opens Mikasa asks if you need help, once per visit (sessionStorage). */
export const GREETING_DELAY_MS = 4000
/** How long she "types" before the words of the greeting appear. */
export const GREETING_TYPING_MS = 900
/** How long the greeting stays before it fades out by itself. */
export const GREETING_SHOW_MS = 8000
const GREETING_LEAVE_MS = 180
const GREETED = 'ht-mikasa-greeted'

type Greeting = 'hidden' | 'typing' | 'shown' | 'leaving'

const stillMotion = () => window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false

/**
 * The Mikasa button at the bottom right of every page, and the chat popup it opens (FR-001).
 * Closed, it is her cut-out face; open, a round button with the close cross. Ctrl+/ (or Cmd+/)
 * toggles it; Escape closes it. A moment after a page opens she offers help once per visit.
 */
export function MikasaDock() {
  const [open, setOpen] = useState(false)
  const [greeting, setGreeting] = useState<Greeting>('hidden')
  // a short offer of help, never stealing the focus: she types for a moment (and hops to catch
  // the eye), then the words arrive; once answered, or the chat opened, it stays away this visit
  useEffect(() => {
    if (sessionStorage.getItem(GREETED)) return
    const timers: number[] = []
    timers.push(
      window.setTimeout(() => {
        if (sessionStorage.getItem(GREETED)) return
        if (stillMotion()) return setGreeting('shown')
        setGreeting('typing')
        timers.push(window.setTimeout(() => setGreeting('shown'), GREETING_TYPING_MS))
      }, GREETING_DELAY_MS),
    )
    return () => timers.forEach((timer) => window.clearTimeout(timer))
  }, [])
  useEffect(() => {
    if (open) sessionStorage.setItem(GREETED, '1')
  }, [open])
  // opening the chat ends the offer, so it cannot pop back when the chat closes
  if (open && greeting !== 'hidden') setGreeting('hidden')
  // left alone, the greeting fades out by itself after a while
  useEffect(() => {
    if (greeting !== 'shown') return
    const timer = window.setTimeout(() => {
      sessionStorage.setItem(GREETED, '1')
      setGreeting(stillMotion() ? 'hidden' : 'leaving')
    }, GREETING_SHOW_MS)
    return () => window.clearTimeout(timer)
  }, [greeting])
  useEffect(() => {
    if (greeting !== 'leaving') return
    const timer = window.setTimeout(() => setGreeting('hidden'), GREETING_LEAVE_MS)
    return () => window.clearTimeout(timer)
  }, [greeting])
  const dismiss = () => {
    sessionStorage.setItem(GREETED, '1')
    setGreeting(stillMotion() ? 'hidden' : 'leaving')
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
      {greeting !== 'hidden' && !open && (
        // no buttons (Ravi, 2026-11-26): a click on it opens the chat (the Mikasa button does the
        // same for the keyboard), and it fades away by itself
        <div
          role="status"
          aria-label="Mikasa says"
          onClick={() => {
            dismiss()
            setOpen(true)
          }}
          className={cn(
            'ht-greeting ht-gradient-fill fixed right-5 bottom-[calc(var(--ht-bottom-bar)+5.5rem)] z-50 w-60 cursor-pointer rounded-2xl rounded-br-md bg-primary px-4 py-3 text-sm font-medium text-primary-foreground shadow-[var(--ht-shadow-overlay)] md:right-6 md:bottom-28',
            greeting === 'leaving' ? 'ht-greeting-out' : 'ht-greeting-in',
          )}
        >
          {greeting === 'typing' ? (
            // the bubble already says who is speaking; the dots are decoration here
            <span aria-hidden>
              <TypingDots />
            </span>
          ) : (
            <p className="mikasa-rise">Hi, I’m Mikasa. Need a hand with your job search?</p>
          )}
        </div>
      )}
      <button
        type="button"
        aria-label="Mikasa"
        aria-expanded={open}
        aria-controls="mikasa-panel"
        aria-keyshortcuts="Control+/"
        title="Ask Mikasa (Ctrl+/)"
        onClick={toggle}
        className={cn(
          'ht-mikasa-dock fixed bottom-[calc(var(--ht-bottom-bar)+0.75rem)] right-4 z-50 md:bottom-5 md:right-5 grid size-16 place-items-center rounded-full outline-none',
          // open: the round accent-gradient button with the cross; closed: her face alone
          open && 'ht-gradient-fill bg-primary text-primary-foreground',
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
          {/* her face floats gently, tilts on hover and hops when she speaks (still for reduced
              motion) */}
          <span
            className={cn('ht-mikasa-float block size-16', greeting === 'typing' && 'ht-mikasa-hop')}
          >
            <MikasaAvatar className="size-16" />
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
