import { useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import {
  type Draft,
  type DraftKind,
  useCreateDraft,
  useDrafts,
  useEditDraft,
  useRecipients,
  useRemoveDraft,
} from './api'

const input = 'rounded-md border border-muted-foreground bg-background px-3 py-1.5 text-sm'
const LIMIT = 200
const SOMEONE_ELSE = '__typed__'

export function InjectionNotice({ signals }: { signals: unknown[] | undefined }) {
  if (!signals || signals.length === 0) return null
  return (
    <p role="note" className="rounded-md bg-surface p-2 text-sm text-danger">
      This posting contains text that looks like instructions to an AI. HireTitan ignored it.
    </p>
  )
}

function DraftCard({ jobId, draft, kind }: { jobId: string; draft: Draft; kind: DraftKind }) {
  const edit = useEditDraft(jobId)
  const create = useCreateDraft(jobId)
  const remove = useRemoveDraft(jobId)
  const [text, setText] = useState(draft.text ?? '')
  // the server's text this card last took; a newer one replaces the box only if it is untouched
  const [seen, setSeen] = useState(draft.text ?? '')
  if ((draft.text ?? '') !== seen) {
    if (text === seen) setText(draft.text ?? '')
    setSeen(draft.text ?? '')
  }
  const [copied, setCopied] = useState<'copied' | 'manual' | null>(null)
  const busy = create.isPending || remove.isPending
  const area = useRef<HTMLTextAreaElement>(null)
  const label = `${draft.recipient.name}${draft.recipient.role ? `, ${draft.recipient.role}` : ''}`
  const limited = kind === 'connection_request'
  const over = limited && text.length > LIMIT
  const changed = text !== (draft.text ?? '')
  const countId = `draft-count-${draft.id}`
  const failure = create.error ?? remove.error

  if (draft.status === 'writing') {
    return (
      <div className="space-y-1 rounded-md bg-surface p-3">
        <p className="text-sm font-medium">{label}</p>
        <p role="status">Writing…</p>
        {draft.paused_reason && <p className="text-sm text-danger">{draft.paused_reason}</p>}
      </div>
    )
  }
  if (draft.status === 'failed') {
    return (
      <div className="space-y-2 rounded-md bg-surface p-3">
        <p className="text-sm font-medium">{label}</p>
        <p role="alert" className="text-sm text-danger">
          {draft.failure_reason ?? 'The draft could not be written.'}
        </p>
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={busy}
          onClick={() => remove.mutate(draft.id)}
        >
          Delete
        </Button>
        {remove.isError && (
          <p role="alert" className="text-sm text-danger">
            {remove.error.message}
          </p>
        )}
      </div>
    )
  }

  async function copy() {
    try {
      await navigator.clipboard.writeText(text)
      setCopied('copied')
    } catch {
      area.current?.focus()
      area.current?.select()
      setCopied('manual')
    }
  }

  function again() {
    if (
      (draft.edited || changed) &&
      !window.confirm('Your edits will be replaced. Write it again?')
    )
      return
    create.mutate({
      kind,
      recipient: draft.recipient.contact_id
        ? { contact_id: draft.recipient.contact_id }
        : {
            name: draft.recipient.name,
            role: draft.recipient.role ?? undefined,
          },
      regenerate: true,
    })
  }

  return (
    <div className="space-y-2 rounded-md border border-divider bg-background p-3">
      <p className="text-sm font-medium">For {label}</p>
      {draft.source === 'fallback' && (
        <p className="text-sm text-muted-small">
          The AI’s wording could not be used, so this is a plain template from your profile.
        </p>
      )}
      <textarea
        ref={area}
        aria-label={`Draft for ${draft.recipient.name}`}
        className={`${input} w-full`}
        rows={limited ? 4 : 10}
        aria-describedby={countId}
        value={text}
        onChange={(event) => {
          setText(event.target.value)
          setCopied(null)
        }}
      />
      <p id={countId} className={`text-sm ${over ? 'text-danger' : 'text-muted-small'}`}>
        {limited ? `${text.length} / ${LIMIT}` : `${text.length} characters`}
        {over && ' · LinkedIn limits a connection request to 200 characters'}
      </p>
      {draft.cited_facts.length > 0 && (
        <div className="text-sm">
          <p className="font-medium">From your profile</p>
          <ul className="list-disc pl-5">
            {draft.cited_facts.map((fact) => (
              <li key={fact.id}>{fact.text}</li>
            ))}
          </ul>
        </div>
      )}
      <div className="flex flex-wrap items-center gap-2">
        <Button
          type="button"
          size="sm"
          disabled={!changed || edit.isPending || text.trim() === ''}
          onClick={() => edit.mutate({ id: draft.id, text })}
        >
          Save
        </Button>
        <Button type="button" variant="outline" size="sm" onClick={() => void copy()}>
          Copy
        </Button>
        <Button type="button" variant="outline" size="sm" disabled={busy} onClick={again}>
          Write again
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          disabled={busy}
          onClick={() => remove.mutate(draft.id)}
        >
          Delete
        </Button>
        {/* always mounted, so the change is announced */}
        <span role="status">
          {copied === 'copied' ? 'Copied' : copied === 'manual' ? 'Press Ctrl+C to copy' : ''}
        </span>
      </div>
      {(edit.error ?? failure) && (
        <p role="alert" className="text-sm text-danger">
          {(edit.error ?? failure)?.message}
        </p>
      )}
      <p className="text-xs text-muted-small">
        HireTitan never sends this. Copy it and send it yourself.
      </p>
    </div>
  )
}

/** The form to ask for one kind of draft, and the drafts already written for the job. */
export function DraftPanel({ jobId, kind }: { jobId: string; kind: DraftKind }) {
  const recipients = useRecipients(jobId)
  const drafts = useDrafts(jobId)
  const create = useCreateDraft(jobId)
  const [who, setWho] = useState('')
  const [name, setName] = useState('')
  const [role, setRole] = useState('')

  const contacts = recipients.data?.contacts ?? []
  const typed = who === SOMEONE_ELSE || (contacts.length === 0 && who === '')
  const contact = contacts.find((c) => c.contact_id === who)
  const ready = typed ? name.trim() !== '' : contact !== undefined
  const mine = (drafts.data?.drafts ?? []).filter((draft) => draft.kind === kind)

  function write() {
    create.mutate({
      kind,
      recipient: typed ? { name, role: role || undefined } : { contact_id: who },
      regenerate: false,
    })
  }

  return (
    <div className="space-y-3 rounded-md bg-surface p-3">
      <InjectionNotice signals={drafts.data?.injection_signals} />
      <div className="flex flex-wrap items-end gap-3">
        {contacts.length > 0 && (
          <label className="flex flex-col gap-1 text-sm">
            Who is it for
            <select
              className={input}
              value={who}
              onChange={(event) => {
                setWho(event.target.value)
              }}
            >
              <option value="">Choose someone</option>
              {contacts.map((c) => (
                <option key={c.contact_id} value={c.contact_id}>
                  {c.name}
                  {c.role ? ` — ${c.role}` : ''}
                </option>
              ))}
              <option value={SOMEONE_ELSE}>Someone else</option>
            </select>
          </label>
        )}
        {typed && (
          <>
            <label className="flex flex-col gap-1 text-sm">
              Name
              <input
                className={input}
                value={name}
                maxLength={120}
                onChange={(event) => setName(event.target.value)}
              />
            </label>
            <label className="flex flex-col gap-1 text-sm">
              Role
              <input
                className={input}
                value={role}
                maxLength={120}
                onChange={(event) => setRole(event.target.value)}
              />
            </label>
          </>
        )}
        <Button type="button" size="sm" disabled={!ready || create.isPending} onClick={write}>
          Write
        </Button>
      </div>
      {create.isError && (
        <p role="alert" className="text-sm text-danger">
          {create.error.message}
        </p>
      )}
      <div className="space-y-3">
        {mine.map((draft) => (
          <DraftCard key={draft.id} jobId={jobId} draft={draft} kind={kind} />
        ))}
      </div>
    </div>
  )
}
