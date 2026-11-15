import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '@/api/client'
import type { components } from '@/api/schema'
import { formatDay } from '@/features/explore/api'
import { type ResumeFile, fetchResumes } from '@/features/profile/api'

export type PipelineResumes = components['schemas']['PipelineResumesOut']
export type ResumeChoice = components['schemas']['ResumeChoiceOut']

/** The name shown for a job's resume: a removed file's name is marked as removed. Empty for none. */
export function resumeName(resume: ResumeChoice | undefined): string {
  if (!resume || resume.state === 'none' || !resume.name) return ''
  return resume.state === 'removed' ? `${resume.name} (removed)` : resume.name
}

/** The name and the day the file was added, for the details of a job. */
export function resumeDetail(resume: ResumeChoice): string {
  const name = resumeName(resume)
  return name === '' ? 'None' : `${name} · added ${formatDay(resume.added_on)}`
}

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
