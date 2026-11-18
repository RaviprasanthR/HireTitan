import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ApiError, apiFetch } from '@/api/client'
import type { components } from '@/api/schema'

export type Tailored = components['schemas']['TailoredOut']
export type ResumeDoc = components['schemas']['ResumeDocument']
export type TailoredListItem = components['schemas']['TailoredListItem']

export const MISSING_TEXT: Record<'not_in_profile' | 'not_in_resume', string> = {
  not_in_profile: 'not in your profile',
  not_in_resume: 'in your profile but not in this resume',
}

export const pdfUrl = (jobId: string) => `/api/v1/jobs/${jobId}/tailored-resume.pdf`
export const docxUrl = (jobId: string) => `/api/v1/jobs/${jobId}/tailored-resume.docx`

/** The job's tailored resume, or `null` when there is none yet. Refetched while it is written. */
export function useTailored(jobId: string) {
  return useQuery({
    queryKey: ['tailored-resume', jobId],
    queryFn: async () => {
      try {
        return await apiFetch<Tailored>(`/jobs/${jobId}/tailored-resume`)
      } catch (error) {
        if (error instanceof ApiError && error.status === 404) return null
        throw error
      }
    },
    refetchInterval: (query) => (query.state.data?.status === 'writing' ? 3000 : false),
  })
}

export function useStartTailor(jobId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (regenerate: boolean) =>
      apiFetch(`/jobs/${jobId}/tailored-resume`, {
        method: 'POST',
        json: { regenerate },
      }),
    onSuccess: () => client.invalidateQueries({ queryKey: ['tailored-resume', jobId] }),
  })
}

export function useSaveTailored(jobId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (document: ResumeDoc) =>
      apiFetch<Tailored>(`/jobs/${jobId}/tailored-resume`, {
        method: 'PUT',
        json: { document },
      }),
    onSuccess: () => client.invalidateQueries({ queryKey: ['tailored-resume'] }),
  })
}

export function useDeleteTailored() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (jobId: string) => apiFetch(`/jobs/${jobId}/tailored-resume`, { method: 'DELETE' }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ['tailored-resume'] })
      void client.invalidateQueries({ queryKey: ['tailored-resumes'] })
    },
  })
}

export function useTailoredList() {
  return useQuery({
    queryKey: ['tailored-resumes'],
    queryFn: () => apiFetch<TailoredListItem[]>('/tailored-resumes'),
  })
}

export function useSaveDescription(jobId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (description: string) =>
      apiFetch(`/jobs/${jobId}/description`, {
        method: 'PUT',
        json: { description },
      }),
    onSuccess: () => client.invalidateQueries({ queryKey: ['jobs'] }),
  })
}
