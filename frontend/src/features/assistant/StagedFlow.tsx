import { Loader2 } from 'lucide-react'
import { useState } from 'react'
import { ApiError } from '@/api/client'
import { Button } from '@/components/ui/button'
import type { DraftKindName, Staged } from './api'
import { MikasaAvatar } from './MikasaAvatar'
import { RefCard } from './RefCard'

const field =
  'w-full rounded-lg border border-white/10 bg-background px-2 py-1.5 text-sm outline-none focus-visible:ring-2 focus-visible:ring-primary/60'

const KINDS: { kind: DraftKindName; label: string }[] = [
  { kind: 'connection_request', label: 'LinkedIn connection message' },
  { kind: 'referral_message', label: 'LinkedIn message' },
  { kind: 'email', label: 'Email' },
]

function problemText(error: unknown): string {
  if (error instanceof ApiError) return error.detail
  return error instanceof Error ? error.message : 'That did not work.'
}

function Ask({ children }: { children: React.ReactNode }) {
  return (
    <div className="mikasa-rise flex items-end gap-2">
      <MikasaAvatar />
      <div className="min-w-0 max-w-[85%] rounded-2xl rounded-bl-md border border-white/[0.06] bg-background px-3 py-2 text-sm shadow-sm">
        {children}
      </div>
    </div>
  )
}

/**
 * The chat's post-to-draft flow (Ravi, 2026-11-24): paste a job post or link, say what to write,
 * get the draft, and only then answer whether to save the job. Nothing is saved before the yes.
 */
export function StagedFlow({
  view,
  onPost,
  onDetails,
  onChoose,
  onSave,
  onDiscard,
}: {
  view: Staged
  onPost: (text: string) => Promise<void>
  onDetails: (title: string, company: string) => Promise<void>
  onChoose: (kind: DraftKindName) => Promise<void>
  onSave: () => Promise<void>
  onDiscard: () => Promise<void>
}) {
  const [text, setText] = useState('')
  const [title, setTitle] = useState('')
  const [company, setCompany] = useState('')
  const [busy, setBusy] = useState<string | null>(null)
  const [problem, setProblem] = useState<string | null>(null)

  async function run(name: string, step: () => Promise<void>) {
    setBusy(name)
    setProblem(null)
    try {
      await step()
    } catch (error) {
      setProblem(problemText(error))
    } finally {
      setBusy(null)
    }
  }

  const spinner = (name: string) =>
    busy === name && <Loader2 aria-hidden className="animate-spin" />

  return (
    <section
      aria-label="Job post"
      className="flex flex-col gap-2 border-t border-white/[0.07] p-3 text-sm"
    >
      {view.step === 'need_post' && (
        <form
          className="flex flex-col gap-2"
          onSubmit={(event) => {
            event.preventDefault()
            void run('post', async () => {
              await onPost(text)
              setText('')
            })
          }}
        >
          <label className="text-xs">
            Job post or link
            <textarea
              className={`${field} min-h-24`}
              value={text}
              maxLength={40000}
              onChange={(event) => setText(event.target.value)}
              onKeyDown={(event) => {
                // Enter sends; Shift+Enter is a new line
                if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
                  event.preventDefault()
                  event.currentTarget.form?.requestSubmit()
                }
              }}
              placeholder="https://… or the whole posting (Enter to continue, Shift+Enter for a new line)"
            />
          </label>
          <p className="text-xs text-muted-small">
            The post is kept only for this draft until you say it can be saved. HireTitan reads its
            title and company; nothing is sent anywhere.
          </p>
          <div className="flex gap-2">
            <Button type="submit" size="sm" disabled={busy !== null || text.trim() === ''}>
              {spinner('post')}
              Continue
            </Button>
            <Button
              type="button"
              size="sm"
              variant="ghost"
              disabled={busy !== null}
              onClick={() => void run('discard', onDiscard)}
            >
              Cancel
            </Button>
          </div>
        </form>
      )}

      {view.step === 'need_details' && (
        <form
          className="flex flex-col gap-2"
          onSubmit={(event) => {
            event.preventDefault()
            void run('details', () => onDetails(title, company))
          }}
        >
          <div className="flex gap-2">
            <label className="flex-1 text-xs">
              Job title
              <input
                className={field}
                value={title}
                maxLength={200}
                onChange={(event) => setTitle(event.target.value)}
              />
            </label>
            <label className="flex-1 text-xs">
              Company
              <input
                className={field}
                value={company}
                maxLength={120}
                onChange={(event) => setCompany(event.target.value)}
              />
            </label>
          </div>
          <div className="flex gap-2">
            <Button
              type="submit"
              size="sm"
              disabled={busy !== null || title.trim() === '' || company.trim() === ''}
            >
              {spinner('details')}
              Continue
            </Button>
            <Button
              type="button"
              size="sm"
              variant="ghost"
              disabled={busy !== null}
              onClick={() => void run('discard', onDiscard)}
            >
              Cancel
            </Button>
          </div>
        </form>
      )}

      {view.step === 'need_kind' && (
        <>
          <ul className="flex flex-wrap gap-1.5">
            {KINDS.map(({ kind, label }) => (
              <li key={kind}>
                <button
                  type="button"
                  disabled={busy !== null}
                  onClick={() => void run(kind, () => onChoose(kind))}
                  className="flex items-center gap-1.5 rounded-full border border-slate bg-transparent px-3 py-1.5 text-xs transition-colors duration-[var(--ht-dur-fast)] hover:border-primary hover:bg-accent-tint disabled:pointer-events-none disabled:opacity-50"
                >
                  {spinner(kind)}
                  {label}
                </button>
              </li>
            ))}
          </ul>
          <Button
            type="button"
            size="xs"
            variant="ghost"
            className="self-start"
            disabled={busy !== null}
            onClick={() => void run('discard', onDiscard)}
          >
            Never mind
          </Button>
        </>
      )}

      {(view.step === 'drafting' || view.step === 'ask_save' || view.step === 'done') &&
        view.draft_ref && <RefCard refText={view.draft_ref} />}

      {view.step === 'ask_save' && (
        <>
          <Ask>
            Would you like me to save <strong>{view.label}</strong> to your jobs?
          </Ask>
          <p className="text-xs text-muted-small">
            If not, the job and this draft are both discarded, so copy the draft first.
          </p>
          <div className="flex gap-2">
            <Button
              type="button"
              size="sm"
              disabled={busy !== null}
              onClick={() => void run('save', onSave)}
            >
              {spinner('save')}
              Yes, save it
            </Button>
            <Button
              type="button"
              size="sm"
              variant="outline"
              disabled={busy !== null}
              onClick={() => void run('discard', onDiscard)}
            >
              {spinner('discard')}
              No, discard
            </Button>
          </div>
        </>
      )}

      {view.step === 'done' && (
        <Button
          type="button"
          size="sm"
          variant="outline"
          className="self-start"
          disabled={busy !== null}
          onClick={() => void run('save', onSave)}
        >
          Done
        </Button>
      )}

      {problem && (
        <p role="alert" className="text-xs text-danger">
          {problem}
        </p>
      )}
    </section>
  )
}
