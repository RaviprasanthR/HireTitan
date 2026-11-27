import { type QueryKey, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'

export const EVENTS_URL = '/api/v1/events'
export const POLL_INTERVAL_MS = 3000

type RunUpdated = { run_id: string }

/** Everything that can change while a run is going; refetched on every poll. */
const POLL_KEYS: QueryKey[] = [
  ['runs'],
  ['review-items'],
  ['resumes'],
  ['status'],
  ['settings'],
  ['profile'],
  ['onboarding'],
  ['jobs'],
  ['search-latest'],
  ['search-run'],
  ['drafts'],
  ['tailored-resume'],
  ['mail'],
]

/**
 * Listens to the server event stream and refetches the matching TanStack Query data.
 * If the stream drops, it polls every 3 s until the stream is back (ADR-08).
 */
export function useEvents(): { connected: boolean } {
  const queryClient = useQueryClient()
  const [connected, setConnected] = useState(false)

  useEffect(() => {
    let poll: ReturnType<typeof setInterval> | undefined
    const invalidate = (...keys: QueryKey[]) => {
      for (const queryKey of keys) void queryClient.invalidateQueries({ queryKey })
    }
    const stopPolling = () => {
      if (poll !== undefined) clearInterval(poll)
      poll = undefined
    }

    if (typeof EventSource === 'undefined') return // e.g. a test environment
    const source = new EventSource(EVENTS_URL)
    source.onopen = () => {
      stopPolling()
      setConnected(true)
      invalidate(...POLL_KEYS) // catch up on anything missed while disconnected
    }
    source.onerror = () => {
      setConnected(false)
      if (poll === undefined) poll = setInterval(() => invalidate(...POLL_KEYS), POLL_INTERVAL_MS)
    }
    source.addEventListener('run.updated', (event) => {
      let data: RunUpdated | null = null
      try {
        data = JSON.parse((event as MessageEvent<string>).data) as RunUpdated
      } catch {
        // a malformed event must not break the listener: refetch the lists instead
      }
      invalidate(
        data?.run_id ? ['runs', data.run_id] : ['runs'],
        ['review-items'],
        ['resumes'],
        ['review'],
        ['settings'],
        ['onboarding'],
      )
    })
    source.addEventListener('status.updated', () => invalidate(['status'], ['settings']))
    source.addEventListener('profile.updated', () => invalidate(['profile'], ['onboarding']))
    // A search batch is stored: the new jobs and the progress appear now (FR-008).
    const searchChanged = () =>
      invalidate(['jobs'], ['search-latest'], ['search-run'], ['search-runs'], ['status'], ['mail'])
    // A draft or tailored resume was written, or could not be (feature 002k).
    const draftChanged = () => invalidate(['drafts'], ['tailored-resume'], ['tailored-resumes'])
    for (const name of [
      'draft.ready',
      'draft.failed',
      'tailored_resume.ready',
      'tailored_resume.failed',
    ])
      source.addEventListener(name, draftChanged)
    // The Gmail connection changed (connected, disconnected, access ended): Settings refreshes.
    source.addEventListener('mail.connection_changed', () => invalidate(['mail']))
    // Mikasa changed something: the pages showing it refresh, in every open tab (002m FR-004).
    source.addEventListener('assistant.changed', (event) => {
      let keys: QueryKey[] = []
      try {
        const data = JSON.parse((event as MessageEvent<string>).data) as { keys?: QueryKey[] }
        keys = Array.isArray(data.keys) ? data.keys : []
      } catch {
        // fall back to the lists Mikasa can change
      }
      invalidate(['assistant'], ...(keys.length ? keys : [['jobs'], ['companies'], ['pipeline']]))
    })
    source.addEventListener('search.batch_done', searchChanged)
    source.addEventListener('search.finished', searchChanged)

    return () => {
      stopPolling()
      source.close()
    }
  }, [queryClient])

  return { connected }
}
