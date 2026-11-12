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

export function useSaveSource(jobId: string) {
  return useWrite(jobId, (input: SourceInput) =>
    apiFetch<Interview>(`/jobs/${jobId}/interview/source`, { method: 'PUT', json: input }),
  )
}
