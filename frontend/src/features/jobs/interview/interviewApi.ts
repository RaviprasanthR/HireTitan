import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiFetch } from '@/api/client'
import type { components } from '@/api/schema'

export type Interview = components['schemas']['InterviewOut']
export type InterviewContact = NonNullable<Interview['contact']>

export type ContactInput = {
  name: string
  role: string
  email: string
  phone: string
  linkedin_url: string
}

export type SourceInput = { kind: 'direct' | 'hiring_firm' | null; firm_name?: string }

const key = (jobId: string) => ['job-interview', jobId] as const

/** What the person recorded about one pipeline job: contact, source, rounds (feature 002e). */
export function useInterview(jobId: string) {
  return useQuery({
    queryKey: key(jobId),
    queryFn: () => apiFetch<Interview>(`/jobs/${jobId}/interview`),
    refetchOnWindowFocus: false,
  })
}

/** Every write answers with the whole interview, so the panel redraws from one response. */
function useWrite<Input>(jobId: string, send: (input: Input) => Promise<Interview>) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: send,
    onSuccess: async (interview) => {
      client.setQueryData(key(jobId), interview)
      await client.invalidateQueries({ queryKey: ['jobs'] }) // the Status column
    },
  })
}

export function useSaveContact(jobId: string) {
  return useWrite(jobId, (input: ContactInput) =>
    apiFetch<Interview>(`/jobs/${jobId}/interview/contact`, { method: 'PUT', json: input }),
  )
}

export type Round = Interview['rounds'][number]
export type RoundKind = Round['kind']
export type RoundState = Round['state']

export const ROUND_KINDS: { value: RoundKind; label: string }[] = [
  { value: 'screening', label: 'Screening' },
  { value: 'technical', label: 'Technical' },
  { value: 'hr', label: 'HR' },
  { value: 'managerial', label: 'Managerial' },
  { value: 'other', label: 'Other' },
]

export const ROUND_STATES: { value: RoundState; label: string }[] = [
  { value: 'scheduled', label: 'Scheduled' },
  { value: 'cleared', label: 'Cleared' },
  { value: 'failed', label: 'Failed' },
]

export type RoundInput = {
  kind: RoundKind
  scheduled_at?: string | null
  interviewers?: string
}

export type RoundChanges = {
  kind?: RoundKind
  scheduled_at?: string | null
  interviewers?: string
  state?: RoundState
  feedback?: string
}

export function useAddRound(jobId: string) {
  return useWrite(jobId, (input: RoundInput) =>
    apiFetch<Interview>(`/jobs/${jobId}/interview/rounds`, { method: 'POST', json: input }),
  )
}

export function useUpdateRound(jobId: string) {
  return useWrite(jobId, ({ id, changes }: { id: string; changes: RoundChanges }) =>
    apiFetch<Interview>(`/interview/rounds/${id}`, { method: 'PATCH', json: changes }),
  )
}

export function useDeleteRound(jobId: string) {
  return useWrite(jobId, (id: string) =>
    apiFetch<Interview>(`/interview/rounds/${id}`, { method: 'DELETE' }),
  )
}

export type QuestionChanges = { question?: string; answer?: string }

export function useAddQuestion(jobId: string) {
  return useWrite(
    jobId,
    ({ roundId, ...input }: { roundId: string; question: string; answer?: string }) =>
      apiFetch<Interview>(`/interview/rounds/${roundId}/questions`, {
        method: 'POST',
        json: input,
      }),
  )
}

export function useUpdateQuestion(jobId: string) {
  return useWrite(jobId, ({ id, changes }: { id: string; changes: QuestionChanges }) =>
    apiFetch<Interview>(`/interview/questions/${id}`, { method: 'PATCH', json: changes }),
  )
}

export function useDeleteQuestion(jobId: string) {
  return useWrite(jobId, (id: string) =>
    apiFetch<Interview>(`/interview/questions/${id}`, { method: 'DELETE' }),
  )
}

export function useSaveSource(jobId: string) {
  return useWrite(jobId, (input: SourceInput) =>
    apiFetch<Interview>(`/jobs/${jobId}/interview/source`, { method: 'PUT', json: input }),
  )
}
