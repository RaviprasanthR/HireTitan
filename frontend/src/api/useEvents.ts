import { type QueryKey, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'

export const EVENTS_URL = '/api/v1/events'
export const POLL_INTERVAL_MS = 3000

type RunUpdated = { run_id: string }

/** Everything that can change while a run is going; refetched on every poll. */
const POLL_KEYS: QueryKey[] = [['runs'], ['review-items'], ['resumes'], ['status'], ['settings'], ['profile']]

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
      )
    })
    source.addEventListener('status.updated', () => invalidate(['status'], ['settings']))
    source.addEventListener('profile.updated', () => invalidate(['profile']))

    return () => {
      stopPolling()
      source.close()
    }
  }, [queryClient])

  return { connected }
}
