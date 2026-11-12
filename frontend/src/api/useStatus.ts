import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '@/api/client'
import type { components } from '@/api/schema'

export type Status = components['schemas']['StatusOut']

/** The AI status and setup checklist; refetched on every `status.updated` event. */
export function useStatus() {
  return useQuery({
    queryKey: ['status'],
    queryFn: () => apiFetch<Status>('/status'),
    refetchOnWindowFocus: false,
  })
}
