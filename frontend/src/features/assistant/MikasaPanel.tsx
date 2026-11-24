import { useQueryClient } from '@tanstack/react-query'
import { Plus, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Link, useLocation } from 'react-router'
import { ApiError } from '@/api/client'
import { Button } from '@/components/ui/button'
import {
  assistantKeys,
  useAssistantStatus,
  useConversations,
  useMessages,
  useStartConversation,
  type StoredMessage,
} from './api'
import { Composer } from './Composer'
import { ReplyText } from './ReplyText'
import { streamTurn, type TurnStreamEvent } from './stream'

export const CONVERSATION_KEY = 'mikasa.conversation'

const UNAVAILABLE: Record<string, string> = {
  key_missing: 'Mikasa needs an AI key.',
  key_rejected: 'Your AI provider rejected the key.',
  out_of_credit: 'Your AI provider says you are out of credit.',
  model_lacks_tools: 'Mikasa needs a model that can use tools.',
}

type Live = { person: string; text: string; notices: string[]; error: string | null }

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

function Message({ message }: { message: StoredMessage }) {
  if (message.author === 'person') {
    return (
      <div className="ml-8 self-end whitespace-pre-wrap rounded-lg bg-primary/15 px-3 py-2 text-sm">
        {message.text}
      </div>
    )
  }
  return (
    <div className="mr-4 rounded-lg bg-background px-3 py-2 text-sm">
      {message.text && <ReplyText text={message.text} />}
      {message.status === 'stopped' && <p className="text-xs text-muted-small">Stopped.</p>}
      {message.status === 'failed' && (
        <p className="text-xs text-danger">
          {(message.error?.provider_message as string | undefined) ??
            'This answer could not be finished.'}
        </p>
      )}
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
  const [chosenId, setConversationId] = useState<string | null>(savedConversation)
  // with no saved conversation, carry on with the most recent one
  const conversationId = chosenId ?? conversations.data?.[0]?.id ?? null
  const messages = useMessages(conversationId)
  const [draft, setDraft] = useState('')
  const [live, setLive] = useState<Live | null>(null)
  const [refusal, setRefusal] = useState<string | null>(null)
  const abort = useRef<AbortController | null>(null)
  const bottom = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    bottom.current?.scrollIntoView?.({ block: 'end' })
  }, [messages.data, live])

  const available = status.data?.available ?? false
  const reason = status.data?.reason ?? null

  async function send(text: string) {
    setRefusal(null)
    let id = conversationId
    if (id === null) {
      id = (await start.mutateAsync()).id
      setConversationId(id)
      saveConversation(id)
    }
    const controller = new AbortController()
    abort.current = controller
    setDraft('')
    setLive({ person: text, text: '', notices: [], error: null })
    const onEvent = (event: TurnStreamEvent) => {
      setLive((current) => {
        if (!current) return current
        if (event.event === 'text') return { ...current, text: current.text + event.data.delta }
        if (event.event === 'notice')
          return { ...current, notices: [...current.notices, event.data.text] }
        if (event.event === 'error') return { ...current, error: event.data.message }
        if (event.event === 'done') return { ...current, text: event.data.text }
        return current
      })
    }
    try {
      await streamTurn(id, text, pathname, onEvent, controller.signal)
    } catch (error) {
      if (error instanceof ApiError) {
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

  function newConversation() {
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
      aria-label="Mikasa"
      className="fixed inset-0 z-40 flex flex-col bg-[var(--ht-surface)] md:static md:inset-auto md:z-auto md:w-[420px] md:shrink-0 md:border-l md:border-white/[0.07]"
    >
      <header className="flex items-center justify-between gap-2 border-b border-divider px-3 py-2">
        <h2 className="text-base font-semibold">Mikasa</h2>
        <div className="flex items-center gap-1">
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
      <div className="flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto p-3" aria-live="polite">
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
          <p className="text-sm text-muted-small">
            Ask me about your jobs, companies, searches or interviews.
          </p>
        )}
        {messages.data?.map((message) => (
          <Message key={message.id} message={message} />
        ))}
        {live && (
          <>
            <div className="ml-8 self-end whitespace-pre-wrap rounded-lg bg-primary/15 px-3 py-2 text-sm">
              {live.person}
            </div>
            <div
              className="mr-4 rounded-lg bg-background px-3 py-2 text-sm"
              data-testid="live-reply"
            >
              {live.text ? (
                <ReplyText text={live.text} />
              ) : (
                <span className="text-muted-small">…</span>
              )}
              {live.notices.map((notice, index) => (
                <p key={index} className="text-xs text-muted-small">
                  {notice}
                </p>
              ))}
              {live.error && <p className="text-xs text-danger">{live.error}</p>}
            </div>
          </>
        )}
        {refusal && (
          <p role="alert" className="text-sm text-danger">
            {refusal}
          </p>
        )}
        <div ref={bottom} />
      </div>
      <Composer
        disabled={!available}
        streaming={live !== null}
        draft={draft}
        onDraftChange={setDraft}
        onSend={(text) => void send(text)}
        onStop={() => abort.current?.abort()}
      />
    </aside>
  )
}
