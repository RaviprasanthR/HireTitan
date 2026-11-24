import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiFetch } from '@/api/client'
import type { components } from '@/api/schema'

export type AssistantStatus = components['schemas']['AssistantStatusOut']
export type Conversation = components['schemas']['ConversationOut']
export type StoredMessage = components['schemas']['MessageOut']
export type RefCard = components['schemas']['RefCardOut']

export const assistantKeys = {
  status: ['assistant', 'status'] as const,
  conversations: ['assistant', 'conversations'] as const,
  messages: (id: string) => ['assistant', 'messages', id] as const,
  ref: (ref: string) => ['assistant', 'ref', ref] as const,
}

/** Whether Mikasa can be used now (FR-024); checked while the panel is open. */
export function useAssistantStatus(enabled: boolean) {
  return useQuery({
    queryKey: assistantKeys.status,
    queryFn: () => apiFetch<AssistantStatus>('/assistant/status'),
    enabled,
  })
}

export function useConversations(enabled: boolean) {
  return useQuery({
    queryKey: assistantKeys.conversations,
    queryFn: () => apiFetch<Conversation[]>('/assistant/conversations'),
    enabled,
  })
}

export function useMessages(conversationId: string | null) {
  return useQuery({
    queryKey: assistantKeys.messages(conversationId ?? 'none'),
    queryFn: () => apiFetch<StoredMessage[]>(`/assistant/conversations/${conversationId}/messages`),
    enabled: conversationId !== null,
  })
}

export function useStartConversation() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: () => apiFetch<{ id: string }>('/assistant/conversations', { method: 'POST' }),
    onSuccess: () => client.invalidateQueries({ queryKey: assistantKeys.conversations }),
  })
}

/** The person's own view of an item Mikasa named; private details stay in the browser. */
export function useRefCard(ref: string) {
  return useQuery({
    queryKey: assistantKeys.ref(ref),
    queryFn: () => apiFetch<RefCard>(`/assistant/refs/${encodeURIComponent(ref)}`),
    staleTime: 30_000,
    retry: false,
  })
}
