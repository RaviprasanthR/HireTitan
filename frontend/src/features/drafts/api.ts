import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiFetch } from '@/api/client'
import type { components } from '@/api/schema'

export type Draft = components['schemas']['DraftOut']
export type DraftsOut = components['schemas']['DraftsOut']
export type Recipients = components['schemas']['RecipientsOut']
export type DraftKind = Draft['kind']
export type RecipientKind = Recipients['kinds'][number]

export const KIND_LABEL: Record<RecipientKind, string> = {
  recruiter: 'Recruiter',
  hiring_manager: 'Hiring manager',
  engineer: 'Engineer',
  other: 'Other',
}

export type RecipientChoice = { contact_id: string } | { name: string; role?: string }

export function useRecipients(jobId: string) {
  return useQuery({
    queryKey: ['drafts', jobId, 'recipients'],
    queryFn: () => apiFetch<Recipients>(`/jobs/${jobId}/recipients`),
  })
}

/** The job's drafts; refetched every 3 s while one is being written (the event stream also does). */
export function useDrafts(jobId: string) {
  return useQuery({
    queryKey: ['drafts', jobId, 'list'],
    queryFn: () => apiFetch<DraftsOut>(`/jobs/${jobId}/drafts`),
    refetchInterval: (query) =>
      query.state.data?.drafts.some((draft) => draft.status === 'writing') ? 3000 : false,
  })
}

export function useCreateDraft(jobId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (input: { kind: DraftKind; recipient: RecipientChoice; regenerate: boolean }) =>
      apiFetch(`/jobs/${jobId}/drafts`, { method: 'POST', json: input }),
    onSuccess: () => client.invalidateQueries({ queryKey: ['drafts', jobId, 'list'] }),
  })
}

export function useEditDraft(jobId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ id, text }: { id: string; text: string }) =>
      apiFetch<Draft>(`/drafts/${id}`, { method: 'PUT', json: { text } }),
    onSuccess: () => client.invalidateQueries({ queryKey: ['drafts', jobId, 'list'] }),
  })
}

export function useRemoveDraft(jobId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => apiFetch(`/drafts/${id}`, { method: 'DELETE' }),
    onSuccess: () => client.invalidateQueries({ queryKey: ['drafts', jobId, 'list'] }),
  })
}
