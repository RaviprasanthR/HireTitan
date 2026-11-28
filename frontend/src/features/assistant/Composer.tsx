import { useState } from 'react'
import { SendHorizontal, Square } from 'lucide-react'
import { Link } from 'react-router'
import { Button } from '@/components/ui/button'

export const MESSAGE_MAX = 2000

type Props = {
  disabled: boolean
  unavailable?: string // why the box is disabled, with a Settings link
  streaming: boolean
  draft: string
  onDraftChange: (text: string) => void
  onSend: (text: string) => void
  onStop: () => void
}

/** The message box: a 2,000-character limit with a count, Send or Stop, and what is sent where. */
export function Composer({ disabled, unavailable, streaming, draft, onDraftChange, onSend, onStop }: Props) {
  const [touched, setTouched] = useState(false)
  const over = draft.length > MESSAGE_MAX
  const canSend = !disabled && !streaming && draft.trim().length > 0 && !over
  const send = () => {
    if (!canSend) return
    onSend(draft)
    setTouched(false)
  }
  return (
    <form
      className="flex flex-col gap-2 border-t border-hairline p-3"
      onSubmit={(event) => {
        event.preventDefault()
        send()
      }}
    >
      <label htmlFor="mikasa-message" className="sr-only">
        Message to Mikasa
      </label>
      <textarea
        id="mikasa-message"
        value={draft}
        rows={3}
        disabled={disabled}
        aria-describedby={disabled && unavailable ? 'mikasa-unavailable' : undefined}
        placeholder="Ask Mikasa about your job search"
        onChange={(event) => {
          setTouched(true)
          onDraftChange(event.target.value)
        }}
        onKeyDown={(event) => {
          if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
            event.preventDefault()
            send()
          }
        }}
        aria-invalid={over || undefined}
        className="w-full resize-none rounded-xl border border-slate bg-background p-2.5 text-sm outline-none transition-shadow focus-visible:ring-2 focus-visible:ring-primary/60"
      />
      {disabled && unavailable && (
        <p id="mikasa-unavailable" className="text-xs text-muted-small">
          {unavailable}{' '}
          <Link to="/settings" className="text-link">
            Settings
          </Link>
        </p>
      )}
      <div className="flex items-center justify-between gap-2">
        <span className={over ? 'text-xs text-danger' : 'text-xs text-muted-small'}>
          {touched || draft ? `${draft.length} / ${MESSAGE_MAX}` : ''}
        </span>
        {streaming ? (
          <Button type="button" variant="outline" size="sm" aria-label="Stop" onClick={onStop}>
            <Square aria-hidden className="fill-current" />
            Stop
          </Button>
        ) : (
          <Button type="submit" size="sm" aria-label="Send" disabled={!canSend}>
            Send
            <SendHorizontal aria-hidden />
          </Button>
        )}
      </div>
      <p className="text-xs text-muted-small">
        What you type here is sent to your AI provider. Contacts, notes and interview details stored
        in HireTitan are not.
      </p>
    </form>
  )
}
