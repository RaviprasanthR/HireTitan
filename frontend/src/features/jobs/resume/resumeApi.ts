import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '@/api/client'
import type { components } from '@/api/schema'
import { type ResumeFile, fetchResumes } from '@/features/profile/api'

export type PipelineResumes = components['schemas']['PipelineResumesOut']

/**
 * The stored files a job's resume can be chosen from: newest first, without a file that was
 * rejected as not a resume. A file still being read, or whose reading failed, is offered, since
 * the person uploaded it as a resume (spec FR-012). The server checks again on every write.
 */
export function offeredResumes(files: ResumeFile[]): ResumeFile[] {
  return files
    .filter((file) => file.parse_status !== 'not_resume')
    .sort((a, b) => b.created_at.localeCompare(a.created_at))
}

/** The person's stored resume files that can be chosen. Shares the Profile page's cache. */
export function useResumeOptions() {
  return useQuery({ queryKey: ['resumes'], queryFn: fetchResumes, select: offeredResumes })
}

/** The resume chosen the last time a job was marked (the choice starts on it), and how many
 *  jobs use each file. Refreshed by every mark, undo and resume change. */
export function usePipelineResumes() {
  return useQuery({
    queryKey: ['pipeline-resumes'],
    queryFn: () => apiFetch<PipelineResumes>('/pipeline/resumes'),
  })
}
