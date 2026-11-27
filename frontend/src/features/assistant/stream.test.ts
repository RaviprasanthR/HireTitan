import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '@/api/client'
import { frameParser, streamTurn, type TurnStreamEvent } from './stream'

function streamOf(pieces: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder()
  return new ReadableStream({
    start(controller) {
      for (const piece of pieces) controller.enqueue(encoder.encode(piece))
      controller.close()
    },
  })
}

describe('stream', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('FR002_parses_events_in_order', async () => {
    const body = [
      ': ping\n\n',
      'event: text\r\ndata: {"delta": "Hel',
      'lo"}\r\n\r\nevent: ref\ndata: {"ref": "job:1"}\n\n',
      'event: unknown\ndata: {}\n\nevent: done\ndata: {"message_id": "m1", ',
      '"status": "complete", "text": "Hello"}\n\n',
    ]
    const fetchMock = vi.fn(async () => new Response(streamOf(body), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    const seen: TurnStreamEvent[] = []

    await streamTurn('c1', 'hi', '/explore', (event) => seen.push(event))

    expect(seen).toEqual([
      { event: 'text', data: { delta: 'Hello' } },
      { event: 'ref', data: { ref: 'job:1' } },
      { event: 'done', data: { message_id: 'm1', status: 'complete', text: 'Hello' } },
    ])
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/assistant/conversations/c1/turns',
      expect.objectContaining({ method: 'POST', body: '{"text":"hi","page":"/explore"}' }),
    )
  })

  it('FR002_refusal_becomes_an_api_error', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(
        async () =>
          new Response(JSON.stringify({ detail: 'Too long', reason: 'too_long' }), {
            status: 422,
            headers: { 'Content-Type': 'application/json' },
          }),
      ),
    )
    const error = await streamTurn('c1', 'x', '/', () => {}).catch((e: unknown) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect((error as ApiError).problem.reason).toBe('too_long')
  })

  it('FR002_abort_stops', async () => {
    const controller = new AbortController()
    vi.stubGlobal(
      'fetch',
      vi.fn(async (_url: string, init: RequestInit) => {
        if (init.signal?.aborted) throw new DOMException('Aborted', 'AbortError')
        return new Response(streamOf([]), { status: 200 })
      }),
    )
    controller.abort()
    await expect(streamTurn('c1', 'x', '/', () => {}, controller.signal)).rejects.toThrow('Aborted')
  })

  it('frames split anywhere are joined', () => {
    const frames: [string, string][] = []
    const parse = frameParser((event, data) => frames.push([event, data]))
    parse('event: te')
    parse('xt\ndata: a\ndata: b\n')
    parse('\n')
    expect(frames).toEqual([['text', 'a\nb']])
  })
})
