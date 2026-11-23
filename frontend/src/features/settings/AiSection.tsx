import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { ApiError, apiFetch } from '@/api/client'
import { useStatus } from '@/api/useStatus'
import { Button } from '@/components/ui/button'

const KEY_STATUS: Record<string, string> = {
  working: 'Working',
  missing: 'Missing',
  rejected: 'Rejected by the provider',
  unreachable: 'Provider could not be reached',
  out_of_credit: 'Out of credit at the provider',
  unknown: 'Being checked',
}

const STATUS_PILL: Record<string, string> = {
  working: 'ht-pill-green',
  missing: 'ht-pill-grey',
  rejected: 'ht-pill-red',
  unreachable: 'ht-pill-yellow',
  out_of_credit: 'ht-pill-orange',
  unknown: 'ht-pill-blue',
}

const SOURCE: Record<string, string> = {
  page: 'Key saved on this page.',
  env: 'Key set in OPENAI_API_KEY in .env, which wins over a key saved here. Change it there and restart HireTitan.',
  none: 'No key yet.',
}

type Beat = { label: string; live: boolean; tone: string }
const FLAT: Beat = { label: 'AI key missing: flat line', live: false, tone: 'ht-ecg-grey' }
const BEAT: Record<string, Beat> = {
  working: { label: 'AI key working: heartbeat', live: true, tone: 'ht-ecg-green' },
  unknown: { label: 'AI key being checked: heartbeat', live: true, tone: 'ht-ecg-blue' },
  missing: { label: 'AI key missing: flat line', live: false, tone: 'ht-ecg-grey' },
  rejected: { label: 'AI key rejected: flat line', live: false, tone: 'ht-ecg-red' },
  unreachable: { label: 'AI provider unreachable: flat line', live: false, tone: 'ht-ecg-yellow' },
  out_of_credit: { label: 'AI key out of credit: flat line', live: false, tone: 'ht-ecg-orange' },
}

// one beat: flat, a small bump, the spike down and up, flat again; drawn twice across the box
const BEAT_PATH =
  'M0 12 H14 l3 -2 l3 2 H26 l3 -9 l4 18 l3 -9 H44 l3 -3 l3 3 H60 ' +
  'H74 l3 -2 l3 2 H86 l3 -9 l4 18 l3 -9 H104 l3 -3 l3 3 H120'

/** A small ECG trace: moving while the key works (or is being checked), flat when it does not. */
function Heartbeat({ status }: { status: string }) {
  const beat = BEAT[status] ?? FLAT
  return (
    <svg
      role="img"
      aria-label={beat.label}
      viewBox="0 0 120 24"
      className={`ht-ecg ${beat.tone}${beat.live ? ' ht-ecg-live' : ''}`}
    >
      {beat.live ? (
        <>
          <path className="ht-ecg-ghost" d={BEAT_PATH} />
          <path className="ht-ecg-trace" d={BEAT_PATH} />
        </>
      ) : (
        <path className="ht-ecg-trace" d="M0 12 H120" />
      )}
    </svg>
  )
}

const FIELD = 'w-full rounded-md border border-muted-foreground bg-background px-3 py-2 text-sm'

function messageOf(error: unknown): string {
  return error instanceof ApiError ? error.detail : 'Something went wrong. Please try again.'
}

/** Settings > AI: the OpenAI key, typed here or set in .env, and its status (002c US6).
 *  The key goes to the server once and is never shown again: only where it comes from. */
export function AiSection() {
  const status = useStatus()
  const queryClient = useQueryClient()
  const [key, setKey] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const removeButton = useRef<HTMLButtonElement>(null)
  const returnFocus = useRef(false)
  const refresh = () => queryClient.invalidateQueries({ queryKey: ['status'] })

  const save = useMutation({
    mutationFn: (value: string) =>
      apiFetch('/settings/ai-key', { method: 'PUT', json: { key: value } }),
    onSuccess: async () => {
      setKey('') // the key never stays on the page
      setSaved(true)
      await refresh()
    },
    onError: (e) => setError(messageOf(e)),
  })
  const remove = useMutation({
    mutationFn: () => {
      setError(null)
      return apiFetch('/settings/ai-key', { method: 'DELETE' })
    },
    onSuccess: async () => {
      setConfirming(false)
      setSaved(false)
      await refresh()
    },
    onError: (e) => setError(messageOf(e)),
  })
  const recheck = useMutation({
    mutationFn: () => {
      setError(null)
      return apiFetch('/status/ai/check', { method: 'POST' })
    },
    onSuccess: refresh,
    onError: (e) => setError(messageOf(e)),
  })

  const ai = status.data?.ai
  const source = ai?.key_source ?? 'none'
  // "Saved. Checking the key…" shows only until the check has answered
  const checking = saved && ai?.status === 'unknown'
  // Cancel puts the focus back on the button that opened the question
  useEffect(() => {
    if (!confirming && returnFocus.current) {
      returnFocus.current = false
      removeButton.current?.focus()
    }
  }, [confirming])
  const editable = ai !== undefined && source !== 'env' && ai.provider !== 'fake'

  function submit(event: React.FormEvent) {
    event.preventDefault()
    if (save.isPending) return
    setError(null)
    setSaved(false)
    save.mutate(key.trim())
  }

  return (
    <section
      id="ai-settings"
      aria-labelledby="ai-heading"
      className="ht-detail-card ht-settings-ai space-y-4 scroll-mt-6"
    >
      <header className="space-y-1">
        <h2 id="ai-heading" className="text-lg font-semibold">
          AI
        </h2>
        <p className="text-sm text-muted-small">
          Your OpenAI key reads resumes, checks jobs against your profile and writes drafts.
        </p>
      </header>
      {status.isPending && (
        <p role="status" className="text-sm">
          Loading…
        </p>
      )}
      {status.isError && (
        <p role="alert" className="text-sm">
          Could not load the AI status.
        </p>
      )}
      {ai && (
        <>
          <div className="flex flex-wrap items-center gap-3">
            <Heartbeat status={ai.status} />
            <span className={`ht-pill ${STATUS_PILL[ai.status] ?? 'ht-pill-grey'}`}>
              {KEY_STATUS[ai.status] ?? ai.status}
            </span>
            <span className="text-sm text-muted-small">{SOURCE[source] ?? ''}</span>
          </div>
          {ai.message && <p className="text-sm text-warning">{ai.message}</p>}
          {editable && (
            <form onSubmit={submit} className="space-y-2" aria-label="AI key">
              <label htmlFor="ai-key" className="block text-sm font-medium">
                {source === 'page' ? 'Replace the key' : 'OpenAI API key'}
              </label>
              <div className="flex flex-wrap gap-3">
                <input
                  id="ai-key"
                  type="password"
                  autoComplete="off"
                  spellCheck={false}
                  value={key}
                  placeholder={source === 'page' ? 'Paste a new key to replace it' : 'sk-…'}
                  onChange={(e) => setKey(e.target.value)}
                  aria-invalid={error !== null}
                  aria-describedby="ai-key-help"
                  className={`${FIELD} max-w-md flex-1`}
                />
                <Button type="submit" disabled={save.isPending || key.trim() === ''}>
                  Save key
                </Button>
              </div>
              <p id="ai-key-help" className="text-xs text-muted-small">
                Stored only on this computer, readable by you. It is never shown here again.
              </p>
            </form>
          )}
          {checking && (
            <p role="status" aria-label="Key result" className="text-sm text-success">
              Saved. Checking the key…
            </p>
          )}
          {error && (
            <p role="alert" className="text-sm text-danger">
              {error}
            </p>
          )}
          <div className="flex flex-wrap gap-3">
            <Button
              type="button"
              variant="outline"
              disabled={recheck.isPending}
              onClick={() => recheck.mutate()}
            >
              Check again
            </Button>
            {editable && source === 'page' && !confirming && (
              <Button
                ref={removeButton}
                type="button"
                variant="outline"
                onClick={() => setConfirming(true)}
              >
                Remove key
              </Button>
            )}
          </div>
          {confirming && (
            <div role="group" aria-label="Remove the key?" className="space-y-2 rounded-md border border-divider p-3">
              <p className="text-sm">
                Without a key, AI tasks pause until you add one again. Remove the key?
              </p>
              <div className="flex gap-3">
                <Button
                  type="button"
                  variant="danger"
                  autoFocus
                  disabled={remove.isPending}
                  onClick={() => remove.mutate()}
                >
                  Yes, remove the key
                </Button>
                <Button
                  type="button"
                  variant="cancel"
                  onClick={() => {
                    returnFocus.current = true
                    setConfirming(false)
                  }}
                >
                  Cancel
                </Button>
              </div>
            </div>
          )}
        </>
      )}
    </section>
  )
}
