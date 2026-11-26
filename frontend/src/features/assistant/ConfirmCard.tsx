import { Loader2 } from 'lucide-react'
import { useState } from 'react'
import { ApiError } from '@/api/client'
import { Button } from '@/components/ui/button'
import type { CardData } from './stream'
import type { CardEdit } from './changes'

type Props = {
  card: CardData
  onConfirm: (cardId: string, edits: CardEdit[]) => Promise<void>
  onCancel: (cardId: string) => Promise<void>
}

const DONE: Record<string, string> = {
  applied: 'Done.',
  cancelled: 'Cancelled. Nothing changed.',
  expired: 'This card expired. Nothing changed; ask Mikasa again.',
  failed: 'This could not be done. Nothing changed.',
}

/** A risky change waiting for the person (FR-010, FR-011): nothing changes until Confirm. */
export function ConfirmCard({ card, onConfirm, onCancel }: Props) {
  const [values, setValues] = useState<Record<string, unknown>[]>(() =>
    card.items.map((item) => ({ ...item.args })),
  )
  const [state, setState] = useState(card.state ?? 'proposed')
  const [busy, setBusy] = useState(false)
  const [problem, setProblem] = useState<string | null>(null)
  const [shownAt] = useState(() => Date.now()) // the server checks expiry again on confirm
  const open = state === 'proposed' && new Date(card.expires_at).getTime() > shownAt

  const act = async (what: 'confirm' | 'cancel') => {
    setBusy(true)
    setProblem(null)
    try {
      if (what === 'confirm') {
        const edits = card.items.flatMap((item, index) => {
          const args = Object.fromEntries(item.editable.map((key) => [key, values[index]?.[key]]))
          return item.editable.length ? [{ index, args }] : []
        })
        await onConfirm(card.card_id, edits)
        setState('applied')
      } else {
        await onCancel(card.card_id)
        setState('cancelled')
      }
    } catch (error) {
      const reason = error instanceof ApiError ? (error.problem.reason as string) : ''
      if (reason === 'stale' || reason === 'expired') setState('expired')
      setProblem(error instanceof Error ? error.message : 'That did not work.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div
      role="group"
      aria-label="Confirm this change"
      className="mikasa-rise my-2 ml-9 rounded-xl border border-warning/50 bg-background p-3 text-sm"
    >
      <p className="font-medium">{card.summary}</p>
      {open &&
        card.items.map((item, index) =>
          item.editable.map((key) => {
            const value = values[index]?.[key]
            const set = (next: unknown) =>
              setValues((was) => was.map((v, i) => (i === index ? { ...v, [key]: next } : v)))
            return (
              <label key={`${index}-${key}`} className="mt-2 flex items-center gap-2 text-xs">
                <span className="w-28 text-muted-small">{key.replace(/_/g, ' ')}</span>
                {typeof value === 'boolean' ? (
                  <input
                    type="checkbox"
                    checked={value}
                    onChange={(event) => set(event.target.checked)}
                  />
                ) : (
                  <input
                    className="flex-1 rounded border border-divider bg-background px-2 py-1"
                    value={value === null || value === undefined ? '' : String(value)}
                    onChange={(event) => set(event.target.value || null)}
                  />
                )}
              </label>
            )
          }),
        )}
      {open ? (
        <div className="mt-2 flex gap-2">
          <Button type="button" size="sm" disabled={busy} onClick={() => void act('confirm')}>
            {busy && <Loader2 aria-hidden className="animate-spin" />}
            Confirm
          </Button>
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={busy}
            onClick={() => void act('cancel')}
          >
            Cancel
          </Button>
        </div>
      ) : (
        <p className="mt-1 text-xs text-muted-small">{DONE[state] ?? DONE.expired}</p>
      )}
      {problem && (
        <p role="alert" className="mt-1 text-xs text-danger">
          {problem}
        </p>
      )}
    </div>
  )
}
