import { useMutation } from '@tanstack/react-query'
import { apiFetch } from '@/api/client'
import { type JobDetail, useRefreshing } from '@/features/explore/api'
import { type PipelineKind, showUndo } from './appliedStore'

/**
 * Marks a job applied or inquired with the day chosen (left out: the server's today). `resume` is
 * the "Resume used" choice: a stored file's id, `null` for None, or left out when the choice is
 * not shown, so the server keeps the job's resume and the last choice as they are.
 */
export function useMarkPipeline(kind: PipelineKind) {
  const refresh = useRefreshing()
  return useMutation({
    mutationFn: ({ id, day, resume }: { id: string; day?: string; resume?: string | null }) => {
      const body: Record<string, unknown> = {}
      if (day) body[kind === 'applied' ? 'applied_on' : 'inquired_on'] = day
      if (resume !== undefined) body.resume_file_id = resume
      return apiFetch<JobDetail>(`/jobs/${id}/${kind}`, {
        method: 'POST',
        json: Object.keys(body).length > 0 ? body : undefined,
      })
    },
    onSuccess: async (job) => {
      showUndo({ id: job.id, title: job.title, kind })
      await refresh()
    },
  })
}

export function useUndoPipeline(kind: PipelineKind) {
  const refresh = useRefreshing()
  return useMutation({
    mutationFn: (id: string) => apiFetch<JobDetail>(`/jobs/${id}/${kind}`, { method: 'DELETE' }),
    onSuccess: async () => {
      showUndo(null)
      await refresh()
    },
  })
}
