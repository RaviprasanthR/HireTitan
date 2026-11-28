import { useQueryClient } from '@tanstack/react-query'
import { History, Plus, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Link, useLocation } from 'react-router'
import { ApiError } from '@/api/client'
import { Button } from '@/components/ui/button'
import {
  assistantKeys,
  useAssistantStatus,
  useClearConversations,
  useConversations,
  useMessages,
  useStaged,
  useStartConversation,
  type QuickAction,
  type StoredMessage,
} from './api'
import { ChangeNotice } from './ChangeNotice'
import { useAssistantChanges } from './changes'
import { Composer } from './Composer'
import { ConfirmCard } from './ConfirmCard'
import { ConversationList } from './ConversationList'
import { PasteForm } from './PasteForm'
import { MikasaAvatar } from './MikasaAvatar'
import { QuickActions, StatusForm } from './QuickActions'
import { StagedFlow } from './StagedFlow'
import { TypingDots } from './TypingDots'
import { ReplyText } from './ReplyText'
import { streamTurn, type CardData, type ChangeData, type TurnStreamEvent } from './stream'

export const CONVERSATION_KEY = 'mikasa.conversation'

const UNAVAILABLE: Record<string, string> = {
  key_missing: 'Mikasa needs an AI key.',
  key_rejected: 'Your AI provider rejected the key.',
  out_of_credit: 'Your AI provider says you are out of credit.',
  model_lacks_tools: 'Mikasa needs a model that can use tools.',
}

type Live = {
  person: string
  text: string
  notices: string[]
  error: string | null
  changes: ChangeData[]
  cards: CardData[]
  done: boolean // the reply is complete: the caret stops
}

type Acts = ReturnType<typeof useAssistantChanges>

function Outcomes({
  cards,
  changes,
  acts,
}: {
  cards: CardData[]
  changes: ChangeData[]
  acts: Acts
}) {
  return (
    <>
      {changes.map((change) => (
        <ChangeNotice key={change.change_id} change={change} onUndo={acts.undo} />
      ))}
      {cards.map((card) => (
        <ConfirmCard
          key={card.card_id}
          card={card}
          onConfirm={acts.confirm}
          onCancel={acts.cancel}
        />
      ))}
    </>
  )
}

function problemText(error: unknown): string {
  if (error instanceof ApiError) return error.detail
  return error instanceof Error ? error.message : 'That did not work.'
}

function savedConversation(): string | null {
  try {
    return localStorage.getItem(CONVERSATION_KEY)
  } catch {
    return null
  }
}

function saveConversation(id: string | null) {
  try {
    if (id) localStorage.setItem(CONVERSATION_KEY, id)
    else localStorage.removeItem(CONVERSATION_KEY)
  } catch {
    // private browsing: the conversation is kept on the server anyway
  }
}

function Message({ message, acts }: { message: StoredMessage; acts: Acts }) {
  if (message.author === 'person') {
    return (
      <>
        <div className="mikasa-rise ml-10 self-end whitespace-pre-wrap rounded-2xl rounded-br-md bg-primary px-3 py-2 text-sm text-primary-foreground">
          {message.text}
        </div>
        <Outcomes
          cards={(message.cards ?? []) as unknown as CardData[]}
          changes={(message.changes ?? []) as unknown as ChangeData[]}
          acts={acts}
        />
      </>
    )
  }
  return (
    <div className="mikasa-rise flex items-end gap-2">
      <MikasaAvatar />
      <div className="min-w-0 max-w-[85%] rounded-2xl rounded-bl-md border border-hairline bg-background px-3 py-2 text-sm">
        {message.text && <ReplyText text={message.text} />}
        {message.status === 'stopped' && <p className="text-xs text-muted-small">Stopped.</p>}
        {message.status === 'failed' && (
          <p className="text-xs text-danger">
            {(message.error?.provider_message as string | undefined) ??
              'This answer could not be finished.'}
          </p>
        )}
      </div>
    </div>
  )
}

/** Mikasa's panel: beside the page, never over it (FR-001). */
export function MikasaPanel({ onClose }: { onClose: () => void }) {
  const client = useQueryClient()
  const { pathname } = useLocation()
  const status = useAssistantStatus(true)
  const conversations = useConversations(true)
  const start = useStartConversation()
  const clear = useClearConversations()
  const [history, setHistory] = useState(false)
  const [chosenId, setConversationId] = useState<string | null>(savedConversation)
  // with no saved conversation, carry on with the most recent one
  const conversationId = chosenId ?? conversations.data?.[0]?.id ?? null
  const messages = useMessages(conversationId)
  const acts = useAssistantChanges(conversationId)
  const staged = useStaged(conversationId)
  const [draft, setDraft] = useState('')
  const [live, setLive] = useState<Live | null>(null)
  const [refusal, setRefusal] = useState<string | null>(null)
  const [postingRefused, setPostingRefused] = useState<string | null>(null)
  const [pasting, setPasting] = useState(false)
  const [typing, setTyping] = useState(false) // the text box opens only when asked for (FR-029)
  const [form, setForm] = useState<QuickAction | null>(null) // the status form, when it is open
  const abort = useRef<AbortController | null>(null)
  const bottom = useRef<HTMLDivElement | null>(null)
  const heading = useRef<HTMLHeadingElement | null>(null)
  // opening the chat moves focus into it, so a keyboard user does not tab past it (WCAG 2.4.3)
  useEffect(() => {
    heading.current?.focus()
  }, [])

  useEffect(() => {
    bottom.current?.scrollIntoView?.({ block: 'end' })
  }, [messages.data, live])

  const available = status.data?.available ?? false
  const reason = status.data?.reason ?? null

  async function send(text: string) {
    setRefusal(null)
    if (/^\s*https?:\/\/\S+\s*$/.test(text)) {
      setDraft('')
      await holdPost(text).catch((error: unknown) => setRefusal(problemText(error)))
      return
    }
    const id = await ensureConversation()
    const controller = new AbortController()
    abort.current = controller
    setDraft('')
    setLive({
      person: text,
      text: '',
      notices: [],
      error: null,
      changes: [],
      cards: [],
      done: false,
    })
    const onEvent = (event: TurnStreamEvent) => {
      setLive((current) => {
        if (!current) return current
        if (event.event === 'text') return { ...current, text: current.text + event.data.delta }
        if (event.event === 'notice')
          return { ...current, notices: [...current.notices, event.data.text] }
        if (event.event === 'error') return { ...current, error: event.data.message }
        if (event.event === 'done') return { ...current, text: event.data.text, done: true }
        if (event.event === 'change')
          return { ...current, changes: [...current.changes, event.data] }
        if (event.event === 'card') return { ...current, cards: [...current.cards, event.data] }
        return current
      })
    }
    try {
      await streamTurn(id, text, pathname, onEvent, controller.signal)
    } catch (error) {
      if (error instanceof ApiError && error.problem.reason === 'looks_like_posting') {
        // a pasted job post: kept for a draft, never sent to the AI
        setDraft('')
        await holdPost(text).catch((held: unknown) => {
          setRefusal(problemText(held))
          setDraft(text)
        })
      } else if (error instanceof ApiError) {
        setRefusal(error.detail)
        setDraft(text) // nothing was sent: the person keeps what they wrote
      }
      // an abort is the Stop button: the server kept what was written
    } finally {
      abort.current = null
      setLive(null)
      await client.invalidateQueries({ queryKey: assistantKeys.messages(id) })
      await client.invalidateQueries({ queryKey: assistantKeys.conversations })
    }
  }

  /** The open conversation, started now if there is none or the remembered one is gone (a
   * conversation can be deleted, or the database reset, while the browser still remembers it). */
  async function ensureConversation(): Promise<string> {
    const known = conversations.data
    if (conversationId !== null && (!known || known.some((c) => c.id === conversationId))) {
      return conversationId
    }
    const id = (await start.mutateAsync()).id
    setConversationId(id)
    saveConversation(id)
    return id
  }

  /** A quick action (FR-029): a draft starts the post-to-draft flow; the others open a form. */
  function pick(action: QuickAction) {
    setRefusal(null)
    if (action.form === 'paste') setPasting(true)
    else if (action.form === 'status') setForm(action)
    else if (action.draft_kind) {
      const kind = action.draft_kind
      void ensureConversation()
        .then((id) => acts.staged.begin(id, kind))
        .catch((error: unknown) =>
          setRefusal(error instanceof Error ? error.message : 'That did not work.'),
        )
    }
  }

  /** A job post or link typed or pasted into the box: kept for a draft, never sent to the AI. */
  async function holdPost(text: string) {
    await acts.staged.post(await ensureConversation(), text)
  }

  function openConversation(id: string) {
    abort.current?.abort()
    setConversationId(id)
    saveConversation(id)
    setLive(null)
    setHistory(false)
  }

  function clearAll() {
    clear.mutate(undefined, {
      onSuccess: () => {
        abort.current?.abort()
        setConversationId(null)
        saveConversation(null)
        setLive(null)
        setHistory(false)
      },
    })
  }

  function newConversation() {
    setHistory(false)
    abort.current?.abort()
    setConversationId(null)
    saveConversation(null)
    setLive(null)
    setRefusal(null)
    start.mutate(undefined, {
      onSuccess: ({ id }) => {
        setConversationId(id)
        saveConversation(id)
      },
    })
  }

  return (
    <aside
      id="mikasa-panel"
      aria-label="Mikasa"
      className="mikasa-pop fixed bottom-[calc(var(--ht-bottom-bar)+5rem)] right-5 z-40 flex h-[min(640px,calc(100dvh-var(--ht-bottom-bar)-9rem))] md:bottom-24 md:h-[min(640px,calc(100dvh-8rem))] w-[min(420px,calc(100vw-2.5rem))] flex-col overflow-hidden rounded-2xl bg-surface shadow-[var(--ht-shadow-overlay)] max-sm:inset-x-2 max-sm:w-auto"
    >
      <header className="flex items-center justify-between gap-2 border-b border-hairline px-3 py-2.5">
        <div className="flex items-center gap-2.5">
          <MikasaAvatar className="size-9" />
          <div>
            <h2 ref={heading} tabIndex={-1} className="text-sm font-semibold leading-tight outline-none">
              Mikasa
            </h2>
            <p className="text-xs leading-tight text-muted-small">Your job-search assistant</p>
          </div>
        </div>
        <div className="flex items-center gap-1">
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            aria-label="History"
            aria-pressed={history}
            onClick={() => setHistory((open) => !open)}
          >
            <History aria-hidden />
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={newConversation}
            disabled={live !== null}
          >
            <Plus aria-hidden />
            New conversation
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            aria-label="Close Mikasa"
            onClick={onClose}
          >
            <X aria-hidden />
          </Button>
        </div>
      </header>
      {history && (
        <ConversationList
          conversations={conversations.data ?? []}
          openId={conversationId}
          onOpen={openConversation}
          onClearAll={clearAll}
        />
      )}
      <div className={history ? 'hidden' : 'contents'}>
      <div className="flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto p-3" aria-busy={live !== null}>
        {/* one short announcement instead of every streamed word (WCAG 4.1.3) */}
        <p role="status" className="sr-only">
          {live ? 'Mikasa is replying' : ''}
        </p>
        {status.data && !available && (
          <div role="alert" className="rounded-md border border-divider p-3 text-sm">
            <p>{UNAVAILABLE[reason ?? ''] ?? 'Mikasa cannot answer right now.'}</p>
            {status.data.provider_message && (
              <p className="text-xs text-muted-small">{status.data.provider_message}</p>
            )}
            <Link to="/settings" className="text-link text-sm">
              Open Settings
            </Link>
          </div>
        )}
        {(messages.data ?? []).length === 0 && !live && available && (
          <div className="mikasa-rise flex flex-col items-center gap-2 px-4 py-6 text-center">
            <MikasaAvatar className="size-14" />
            <p className="text-sm font-medium">Hi, I'm Mikasa.</p>
            <p className="text-sm text-muted-small">
              Ask me about your jobs, companies, searches or interviews.
            </p>
          </div>
        )}
        {messages.data?.map((message) => (
          <Message key={message.id} message={message} acts={acts} />
        ))}
        {live && (
          <>
            <div className="mikasa-rise ml-10 self-end whitespace-pre-wrap rounded-2xl rounded-br-md bg-primary px-3 py-2 text-sm text-primary-foreground">
              {live.person}
            </div>
            <div className="mikasa-rise flex items-end gap-2">
              <MikasaAvatar />
              <div
                className="min-w-0 max-w-[85%] rounded-2xl rounded-bl-md border border-hairline bg-background px-3 py-2 text-sm"
                data-testid="live-reply"
              >
                {live.text ? (
                  <div>
                    <ReplyText text={live.text} />
                    {!live.done && (
                      <span
                        aria-hidden
                        className="mikasa-caret ml-0.5 inline-block h-4 w-0.5 translate-y-0.5 bg-current"
                      />
                    )}
                  </div>
                ) : (
                  !live.error && <TypingDots />
                )}
                {live.notices.map((notice, index) => (
                  <p key={index} className="text-xs text-muted-small">
                    {notice}
                  </p>
                ))}
                {live.error && <p className="text-xs text-danger">{live.error}</p>}
              </div>
            </div>
            <Outcomes cards={live.cards} changes={live.changes} acts={acts} />
          </>
        )}
        {refusal && (
          <div role="alert" className="text-sm text-danger">
            <p>{refusal}</p>
            {postingRefused !== null && (
              <Button type="button" size="sm" variant="outline" onClick={() => setPasting(true)}>
                Paste it as a job description
              </Button>
            )}
          </div>
        )}
        <div ref={bottom} />
      </div>
      {pasting ? (
        <PasteForm
          initialDescription={postingRefused ?? ''}
          onClose={() => {
            setPasting(false)
            setPostingRefused(null)
            setRefusal(null)
          }}
          onPaste={async (fields) => {
            const id = await ensureConversation()
            setDraft('')
            return acts.paste(id, fields)
          }}
        />
      ) : form?.form === 'status' ? (
        <StatusForm
          onBack={() => setForm(null)}
          onRun={async (job, status) => acts.status(await ensureConversation(), job, status)}
        />
      ) : staged.data && conversationId ? (
        <StagedFlow
          view={staged.data}
          onPost={(text) => acts.staged.post(conversationId, text)}
          onDetails={(title, company) => acts.staged.details(conversationId, title, company)}
          onChoose={(kind) => acts.staged.choose(conversationId, kind)}
          onSave={() => acts.staged.save(conversationId)}
          onDiscard={() => acts.staged.discard(conversationId)}
        />
      ) : (
        <QuickActions
          disabled={live !== null}
          onPick={pick}
          onTypeInstead={() => setTyping(true)}
          typing={typing}
        />
      )}
      {typing && (
        <Composer
          disabled={!available}
          unavailable={
            status.data ? (UNAVAILABLE[reason ?? ''] ?? 'Mikasa cannot answer right now.') : undefined
          }
          streaming={live !== null}
          draft={draft}
          onDraftChange={setDraft}
          onSend={(text) => void send(text)}
          onStop={() => abort.current?.abort()}
        />
      )}
      </div>
    </aside>
  )
}
