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
  staged: (id: string) => ['assistant', 'staged', id] as const,
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

export function useClearConversations() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: () => apiFetch<undefined>('/assistant/conversations', { method: 'DELETE' }),
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
    // a draft being written fills in by itself
    refetchInterval: (query) => (query.state.data?.subtitle?.includes('writing') ? 2000 : false),
  })
}

export type QuickAction = components['schemas']['QuickActionOut']
export type JobCard = components['schemas']['JobCardOut']
export type JobPage = components['schemas']['JobCardPage']

/** The quick actions the chat offers first (FR-029): a fixed list. */
export function useQuickActions() {
  return useQuery({
    queryKey: ['assistant', 'quick-actions'] as const,
    queryFn: () => apiFetch<QuickAction[]>('/assistant/quick-actions'),
    staleTime: Infinity,
  })
}

/** The jobs a quick form can pick from: the pipeline first, then Explore, each job once. */
export function useJobChoices(enabled: boolean) {
  return useQuery({
    queryKey: ['jobs', 'assistant-choices'] as const,
    enabled,
    queryFn: async () => {
      const [pipeline, explore] = await Promise.all([
        apiFetch<JobPage>('/jobs?list=pipeline'),
        apiFetch<JobPage>('/jobs?list=explore'),
      ])
      const seen = new Set<string>()
      return [...pipeline.items, ...explore.items].filter((job) =>
        seen.has(job.id) ? false : (seen.add(job.id), true),
      )
    },
  })
}

export type Staged = components['schemas']['StagedOut']
export type DraftKindName = NonNullable<Staged['kind']>

/** Where the post-to-draft flow of a conversation stands (null when nothing is held). A draft
 * being written refreshes the step by itself. */
export function useStaged(conversationId: string | null) {
  return useQuery({
    queryKey: assistantKeys.staged(conversationId ?? 'none'),
    queryFn: () => apiFetch<Staged | null>(`/assistant/conversations/${conversationId}/staged`),
    enabled: conversationId !== null,
    refetchInterval: (query) => (query.state.data?.step === 'drafting' ? 2000 : false),
  })
}
