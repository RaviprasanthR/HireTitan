import { useMutation } from '@tanstack/react-query'
import { apiFetch } from '@/api/client'
import { type JobDetail, useRefreshing } from '@/features/explore/api'
import { type PipelineKind, showUndo } from './appliedStore'

/** Marks a job applied or inquired with the day chosen (left out: the server's today). */
export function useMarkPipeline(kind: PipelineKind) {
  const refresh = useRefreshing()
  return useMutation({
    mutationFn: ({ id, day }: { id: string; day?: string }) =>
      apiFetch<JobDetail>(`/jobs/${id}/${kind}`, {
        method: 'POST',
        json: day ? { [kind === 'applied' ? 'applied_on' : 'inquired_on']: day } : undefined,
      }),
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
