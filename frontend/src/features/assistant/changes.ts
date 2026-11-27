import { useQueryClient } from '@tanstack/react-query'
import { apiFetch } from '@/api/client'
import { assistantKeys, type DraftKindName } from './api'

export type PasteFields = { url: string; description: string; title?: string; company?: string }
export type QuickStatus = 'applied' | 'inquired' | 'not_applied' | 'not_inquired'
export type CardEdit = { index: number; args: Record<string, unknown> }

/** Mikasa's changes and cards (FR-010 to FR-014). After each one, the lists it touched refresh. */
export function useAssistantChanges(conversationId: string | null) {
  const client = useQueryClient()
  // `id` is given by calls that may have just started the conversation: the id this hook was
  // made with is still null then, and the new messages must still load.
  const refresh = async (keys: string[][] = [], id: string | null = conversationId) => {
    for (const key of [...keys, ['jobs']]) await client.invalidateQueries({ queryKey: key })
    if (id) await client.invalidateQueries({ queryKey: assistantKeys.messages(id) })
  }
  // the held post, the chat's messages and, after a yes, the job lists
  const refreshStaged = async (id: string, keys: string[][] = []) => {
    await client.invalidateQueries({ queryKey: assistantKeys.staged(id) })
    await refresh(keys, id)
  }
  return {
    confirm: async (cardId: string, edits: CardEdit[]) => {
      const done = await apiFetch<{ results: { invalidate?: string[][]; refs?: string[] }[] }>(
        `/assistant/cards/${cardId}/confirm`,
        { method: 'POST', json: { items: edits } },
      )
      await refresh(done.results.flatMap((result) => result.invalidate ?? []))
      return done.results.flatMap((result) => result.refs ?? [])
    },
    cancel: async (cardId: string) => {
      await apiFetch(`/assistant/cards/${cardId}/cancel`, { method: 'POST' })
      await refresh()
    },
    undo: async (changeId: string) => {
      await apiFetch(`/assistant/changes/${changeId}/undo`, { method: 'POST' })
      await refresh([['pipeline'], ['companies']])
    },
    status: async (id: string, job: string, status: QuickStatus) => {
      const done = await apiFetch<{ changes: { invalidate?: string[][] }[] }>(
        `/assistant/conversations/${id}/quick/status`,
        { method: 'POST', json: { job, status } },
      )
      await refresh(
        done.changes.flatMap((change) => change.invalidate ?? []),
        id,
      )
    },
    staged: {
      begin: async (id: string, kind: DraftKindName) => {
        await apiFetch(`/assistant/conversations/${id}/staged/begin`, {
          method: 'POST',
          json: { kind },
        })
        await refreshStaged(id)
      },
      post: async (id: string, text: string) => {
        await apiFetch(`/assistant/conversations/${id}/staged/post`, {
          method: 'POST',
          json: { text },
        })
        await refreshStaged(id)
      },
      details: async (id: string, title: string, company: string) => {
        await apiFetch(`/assistant/conversations/${id}/staged/details`, {
          method: 'POST',
          json: { title, company },
        })
        await refreshStaged(id)
      },
      choose: async (id: string, kind: DraftKindName) => {
        await apiFetch(`/assistant/conversations/${id}/staged/choose`, {
          method: 'POST',
          json: { kind },
        })
        await refreshStaged(id)
      },
      save: async (id: string) => {
        await apiFetch(`/assistant/conversations/${id}/staged/save`, { method: 'POST' })
        await refreshStaged(id, [['jobs']])
      },
      discard: async (id: string) => {
        await apiFetch(`/assistant/conversations/${id}/staged/discard`, { method: 'POST' })
        await refreshStaged(id)
      },
    },
    paste: async (id: string, fields: PasteFields) => {
      const done = await apiFetch<{ summary: string; change_id?: string; refs?: string[] }>(
        `/assistant/conversations/${id}/paste`,
        { method: 'POST', json: fields },
      )
      await refresh([], id)
      return done
    },
  }
}
