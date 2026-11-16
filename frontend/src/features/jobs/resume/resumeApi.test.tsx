import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { stubApi } from '@/test/api'
import { offeredResumes, useResumeOptions } from './resumeApi'

function file(id: string, over: Record<string, unknown> = {}) {
  return {
    id,
    original_name: `${id}.pdf`,
    parse_status: 'parsed',
    created_at: `2026-11-0${id.length}T09:00:00Z`,
    ...over,
  } as never
}

describe('offeredResumes', () => {
  it('offers the newest first and leaves out a file that is not a resume', () => {
    const files = [
      file('a', { created_at: '2026-11-01T09:00:00Z' }),
      file('b', { created_at: '2026-11-03T09:00:00Z' }),
      file('c', { created_at: '2026-11-02T09:00:00Z', parse_status: 'not_resume' }),
    ]
    expect(offeredResumes(files).map((f) => f.id)).toEqual(['b', 'a'])
  })

  it('treats anything that is not a list as no files (a throwing select loops the page)', () => {
    for (const odd of [undefined, null, {}, { detail: 'x' }, 'text', 42]) {
      expect(offeredResumes(odd as never)).toEqual([])
    }
  })
})

function Probe() {
  const files = useResumeOptions()
  return <p data-testid="state">{`${files.status}:${files.data?.length ?? 'none'}`}</p>
}

describe('useResumeOptions', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('is an empty list, not an error, when the answer is not a list', async () => {
    stubApi(() => ({ job_id: 'a', rounds: [] })) // an answer meant for another endpoint
    render(
      <QueryClientProvider
        client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
      >
        <Probe />
      </QueryClientProvider>,
    )
    await waitFor(() => expect(screen.getByTestId('state')).toHaveTextContent('success:0'))
  })
})
