import { useMutation } from '@tanstack/react-query'
import { apiFetch } from '@/api/client'
import { type JobDetail, useRefreshing } from '@/features/explore/api'
import { showUndo } from './appliedStore'

export function useMarkApplied() {
  const refresh = useRefreshing()
  return useMutation({
    mutationFn: ({ id, appliedOn }: { id: string; appliedOn?: string }) =>
      apiFetch<JobDetail>(`/jobs/${id}/applied`, {
        method: 'POST',
        json: appliedOn ? { applied_on: appliedOn } : undefined,
      }),
    onSuccess: async (job) => {
      showUndo({ id: job.id, title: job.title })
      await refresh()
    },
  })
}

export function useUndoApplied() {
  const refresh = useRefreshing()
  return useMutation({
    mutationFn: (id: string) => apiFetch<JobDetail>(`/jobs/${id}/applied`, { method: 'DELETE' }),
    onSuccess: async () => {
      showUndo(null)
      await refresh()
    },
  })
}
