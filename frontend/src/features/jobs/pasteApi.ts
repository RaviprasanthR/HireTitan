import { useMutation } from '@tanstack/react-query'
import { apiFetch } from '@/api/client'
import type { components } from '@/api/schema'
import { useRefreshing } from '@/features/explore/api'

export type PastedJob = components['schemas']['PasteOut']

export type PasteFields = {
  url: string
  description: string
  title?: string
  company?: string
  location?: string
  link_only?: boolean // 002m: only the link, title and company; the description later
}

export function usePasteJob() {
  const refresh = useRefreshing()
  return useMutation({
    mutationFn: (fields: PasteFields) =>
      apiFetch<PastedJob>('/jobs/paste', { method: 'POST', json: fields }),
    onSuccess: refresh,
  })
}
