import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiFetch } from '@/api/client'
import type { components } from '@/api/schema'

export type JobCard = components['schemas']['JobCardOut']
export type JobDetail = components['schemas']['JobDetailOut']
export type JobPage = components['schemas']['JobCardPage']
export type RunSummary = components['schemas']['SearchRunSummary']
export type RunDetail = components['schemas']['SearchRunOut']
export type RunPage = components['schemas']['SearchRunPage']
export type DuplicatePair = components['schemas']['DuplicatePairOut']
export type DuplicatePage = components['schemas']['DuplicatePage']

export type JobFilters = {
  source: string
  work_mode: string
  city: string
  sort: 'newest' | 'company'
}

export const NO_FILTERS: JobFilters = {
  source: '',
  work_mode: '',
  city: '',
  sort: 'newest',
}

/** Batches of this many companies, as the search reads them (T030). */
export const BATCH_SIZE = 8

function query(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== '') search.set(key, String(value))
  }
  const text = search.toString()
  return text ? `?${text}` : ''
}

export function useJobs(filters: JobFilters) {
  return useInfiniteQuery({
    queryKey: ['jobs', 'explore', filters],
    initialPageParam: '',
    queryFn: ({ pageParam }) =>
      apiFetch<JobPage>(
        `/jobs${query({
          list: 'explore',
          source: filters.source,
          work_mode: filters.work_mode,
          city: filters.city,
          sort: filters.sort,
          cursor: pageParam,
        })}`,
      ),
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    refetchOnWindowFocus: false,
  })
}

export function useJob(id: string) {
  return useQuery({
    queryKey: ['jobs', 'one', id],
    queryFn: () => apiFetch<JobDetail>(`/jobs/${id}`),
  })
}

export function useLatestRun() {
  return useQuery({
    queryKey: ['search-latest'],
    queryFn: () => apiFetch<RunSummary | null>('/search/latest'),
    refetchOnWindowFocus: false,
  })
}

export function useRun(id: string) {
  return useQuery({
    queryKey: ['search-run', id],
    queryFn: () => apiFetch<RunDetail>(`/search/runs/${id}`),
  })
}

export function useRuns() {
  return useInfiniteQuery({
    queryKey: ['search-runs'],
    initialPageParam: '',
    queryFn: ({ pageParam }) => apiFetch<RunPage>(`/search/runs${query({ cursor: pageParam })}`),
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  })
}

export function useSkipped(runId: string) {
  return useInfiniteQuery({
    queryKey: ['search-run', runId, 'skipped'],
    initialPageParam: '',
    queryFn: ({ pageParam }) =>
      apiFetch<JobPage>(`/search/runs/${runId}/skipped${query({ cursor: pageParam })}`),
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  })
}

function useRefreshing() {
  const client = useQueryClient()
  return () =>
    Promise.all(
      [['jobs'], ['search-latest'], ['search-run'], ['search-runs'], ['duplicates']].map(
        (queryKey) => client.invalidateQueries({ queryKey }),
      ),
    )
}

export function useStartSearch() {
  const refresh = useRefreshing()
  return useMutation({
    mutationFn: (mode: 'rules_and_ai' | 'rules_only') =>
      apiFetch<{ search_run_id: string; run_id: string }>('/search/runs', {
        method: 'POST',
        json: { mode },
      }),
    onSuccess: refresh,
  })
}

export function useStopSearch() {
  const refresh = useRefreshing()
  return useMutation({
    mutationFn: (id: string) => apiFetch(`/search/runs/${id}/stop`, { method: 'POST' }),
    onSuccess: refresh,
  })
}

export function useRecheck() {
  const refresh = useRefreshing()
  return useMutation({
    mutationFn: (id: string) =>
      apiFetch<{ run_id: string }>(`/jobs/${id}/recheck`, { method: 'POST' }),
    onSuccess: refresh,
  })
}

export function useRestore() {
  const refresh = useRefreshing()
  return useMutation({
    mutationFn: (id: string) => apiFetch<JobDetail>(`/jobs/${id}/restore`, { method: 'POST' }),
    onSuccess: refresh,
  })
}

export function useDuplicates() {
  return useQuery({
    queryKey: ['duplicates'],
    queryFn: () => apiFetch<DuplicatePage>('/jobs/duplicates'),
    refetchOnWindowFocus: false,
  })
}

export function useDecideDuplicate() {
  const refresh = useRefreshing()
  return useMutation({
    mutationFn: ({ id, action }: { id: string; action: 'merge' | 'dismiss' }) =>
      apiFetch<DuplicatePair>(`/jobs/duplicates/${id}/${action}`, {
        method: 'POST',
      }),
    onSuccess: refresh,
  })
}

export function sourceLabel(kind: string): string {
  switch (kind) {
    case 'company_board':
      return 'Company job board'
    case 'careers_page':
      return 'Careers page'
    case 'gmail_alert':
      return 'Email alert'
    case 'aggregator':
      return 'Job site'
    case 'manual':
      return 'Added by you'
    default:
      return kind
  }
}

/** The reason line of a card, in plain words. */
export function reasonOf(job: JobCard): string {
  return job.decision?.reason ?? ''
}

export function isNotChecked(job: JobCard): boolean {
  return job.decision?.decided_by === 'rules_only_fallback'
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return ''
  return new Date(value).toLocaleDateString('en-GB', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  })
}
