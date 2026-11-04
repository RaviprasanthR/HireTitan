import { apiFetch } from '@/api/client'
import type { components } from '@/api/schema'

export type ResumeFile = components['schemas']['ResumeFileOut']
export type Run = components['schemas']['RunOut']
export type Accepted = components['schemas']['AcceptedOut']
export type Decision = components['schemas']['DecisionIn']['decision']

export type InjectionFlag = {
  rule_id: string
  severity: 'high' | 'medium' | 'low'
  excerpt: string
  location: 'visible' | 'hidden'
}

export const MAX_UPLOAD_BYTES = 5 * 1024 * 1024

const query = (discard: boolean) => (discard ? '?discard_open_review=true' : '')

export const fetchResumes = () => apiFetch<ResumeFile[]>('/resumes')
export const fetchRun = (id: string) => apiFetch<Run>(`/runs/${id}`)

export function uploadResume(file: File, discard = false) {
  const body = new FormData()
  body.append('file', file)
  return apiFetch<Accepted>(`/resumes${query(discard)}`, { method: 'POST', body })
}

export const pasteResume = (text: string, discard = false) =>
  apiFetch<Accepted>(`/resumes/text${query(discard)}`, { method: 'POST', json: { text } })

export const decide = (runId: string, decision: Decision) =>
  apiFetch<{ run_id: string }>(`/runs/${runId}/decision`, { method: 'POST', json: { decision } })

export const retryRun = (runId: string) =>
  apiFetch<{ run_id: string }>(`/runs/${runId}/retry`, { method: 'POST' })

export function injectionFlags(file: ResumeFile | undefined): InjectionFlag[] {
  const flags = (file?.parse_result as { injection_flags?: InjectionFlag[] } | null)?.injection_flags
  return flags ?? []
}
