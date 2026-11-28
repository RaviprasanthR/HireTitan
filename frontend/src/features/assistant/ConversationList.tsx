import { useEffect, useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import type { Conversation } from './api'

/** The person's earlier conversations with Mikasa: open one, or delete them all (after asking). */
export function ConversationList({
  conversations,
  openId,
  onOpen,
  onClearAll,
}: {
  conversations: Conversation[]
  openId: string | null
  onOpen: (id: string) => void
  onClearAll: () => void
}) {
  const [asking, setAsking] = useState(false)
  const keep = useRef<HTMLButtonElement>(null)
  const clearBtn = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    if (asking) keep.current?.focus() // the safe choice gets focus
  }, [asking])
  function cancel() {
    setAsking(false)
    requestAnimationFrame(() => clearBtn.current?.focus())
  }
  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto p-3">
      {conversations.length === 0 ? (
        <p className="text-sm text-muted-small">No earlier conversations.</p>
      ) : (
        <ul aria-label="Conversations" className="flex flex-col gap-1">
          {conversations.map((c) => (
            <li key={c.id}>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="w-full justify-start truncate"
                aria-current={c.id === openId || undefined}
                onClick={() => onOpen(c.id)}
              >
                {c.title ?? 'Untitled conversation'}
              </Button>
            </li>
          ))}
        </ul>
      )}
      {conversations.length > 0 &&
        (asking ? (
          <div
            role="alertdialog"
            aria-label="Clear all"
            aria-describedby="clear-all-text"
            onKeyDown={(e) => e.key === 'Escape' && cancel()}
            className="rounded-md border border-divider p-3 text-sm"
          >
            <p id="clear-all-text">Delete all your conversations with Mikasa? This cannot be undone.</p>
            <div className="mt-2 flex gap-2">
              <Button type="button" size="sm" variant="destructive" onClick={onClearAll}>
                Yes, delete them
              </Button>
              <Button ref={keep} type="button" size="sm" variant="outline" onClick={cancel}>
                Keep them
              </Button>
            </div>
          </div>
        ) : (
          <Button ref={clearBtn} type="button" size="sm" variant="outline" onClick={() => setAsking(true)}>
            Clear all
          </Button>
        ))}
    </div>
  )
}
