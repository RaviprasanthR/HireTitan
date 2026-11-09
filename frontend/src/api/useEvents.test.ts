import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook } from '@testing-library/react'
import { createElement, type ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useEvents } from './useEvents'

class FakeEventSource {
  static instances: FakeEventSource[] = []
  listeners = new Map<string, ((e: MessageEvent) => void)[]>()
  onopen: (() => void) | null = null
  onerror: (() => void) | null = null
  closed = false
  url: string
  constructor(url: string) {
    this.url = url
    FakeEventSource.instances.push(this)
  }
  addEventListener(type: string, fn: (e: MessageEvent) => void) {
    this.listeners.set(type, [...(this.listeners.get(type) ?? []), fn])
  }
  emit(type: string, data: unknown) {
    for (const fn of this.listeners.get(type) ?? []) {
      fn(new MessageEvent(type, { data: JSON.stringify(data) }))
    }
  }
  close() {
    this.closed = true
  }
}

function setup() {
  const client = new QueryClient()
  const invalidate = vi.spyOn(client, 'invalidateQueries')
  const wrapper = ({ children }: { children: ReactNode }) =>
    createElement(QueryClientProvider, { client }, children)
  const hook = renderHook(() => useEvents(), { wrapper })
  const source = FakeEventSource.instances.at(-1)
  if (!source) throw new Error('useEvents did not open an event stream')
  return { invalidate, hook, source }
}

const keys = (spy: { mock: { calls: unknown[][] } }) =>
  spy.mock.calls.map((call) => (call[0] as { queryKey: unknown[] }).queryKey)

beforeEach(() => {
  FakeEventSource.instances = []
  vi.stubGlobal('EventSource', FakeEventSource)
  vi.useFakeTimers()
})

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

describe('useEvents', () => {
  it('connects_to_the_event_stream', () => {
    const { source } = setup()
    expect(source.url).toBe('/api/v1/events')
  })

  it('run_updated_invalidates_that_run_and_the_lists', () => {
    const { invalidate, source } = setup()
    act(() => source.emit('run.updated', { run_id: 'r1', status: 'running' }))
    expect(keys(invalidate)).toEqual(
      expect.arrayContaining([['runs', 'r1'], ['review-items'], ['resumes']]),
    )
  })

  it('status_updated_invalidates_status_and_profile_updated_invalidates_profile', () => {
    const { invalidate, source } = setup()
    act(() => source.emit('status.updated', { ai_status: 'working' }))
    act(() => source.emit('profile.updated', { current_version_id: 'v1' }))
    expect(keys(invalidate)).toEqual(expect.arrayContaining([['status'], ['profile']]))
  })

  it('falls_back_to_polling_on_error', () => {
    const { invalidate, hook, source } = setup()
    act(() => source.onopen?.())
    expect(hook.result.current.connected).toBe(true)

    act(() => source.onerror?.())
    expect(hook.result.current.connected).toBe(false)
    invalidate.mockClear()

    act(() => vi.advanceTimersByTime(3000))
    expect(invalidate).toHaveBeenCalled()
    const first = invalidate.mock.calls.length
    act(() => vi.advanceTimersByTime(3000))
    expect(invalidate.mock.calls.length).toBeGreaterThan(first)
  })

  it('stops_polling_when_the_stream_comes_back', () => {
    const { invalidate, source } = setup()
    act(() => source.onerror?.())
    act(() => source.onopen?.())
    invalidate.mockClear()
    act(() => vi.advanceTimersByTime(9000))
    expect(invalidate).not.toHaveBeenCalled()
  })

  it('closes_the_stream_and_polling_on_unmount', () => {
    const { hook, source, invalidate } = setup()
    act(() => source.onerror?.())
    hook.unmount()
    expect(source.closed).toBe(true)
    invalidate.mockClear()
    act(() => vi.advanceTimersByTime(9000))
    expect(invalidate).not.toHaveBeenCalled()
  })
})

describe('useEvents review fixes', () => {
  it('a_malformed_run_event_is_ignored_instead_of_throwing', () => {
    const { invalidate, source } = setup()
    const before = invalidate.mock.calls.length
    const listener = source.listeners.get('run.updated')?.[0]

    expect(() => listener?.(new MessageEvent('run.updated', { data: 'not json{' }))).not.toThrow()
    expect(keys(invalidate).slice(before)).toContainEqual(['review-items']) // falls back to the lists
  })

  it('a_run_event_also_refreshes_the_open_review', () => {
    const { invalidate, source } = setup()

    act(() => source.emit('run.updated', { run_id: 'r1' }))

    expect(keys(invalidate)).toContainEqual(['review'])
  })

  it('FR008_search_events_refresh_jobs_and_progress', () => {
    const { source, invalidate } = setup()
    invalidate.mockClear()

    act(() => source.emit('search.batch_done', { search_run_id: 's1', batches_done: 1 }))
    act(() => source.emit('search.finished', { search_run_id: 's1', outcome: 'finished' }))

    const refreshed = keys(invalidate).map((k) => k[0])
    expect(refreshed).toEqual(expect.arrayContaining(['jobs', 'search-latest', 'search-run']))
    expect(invalidate.mock.calls.length).toBeGreaterThanOrEqual(10)
  })
})
