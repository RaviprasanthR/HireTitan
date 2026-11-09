import { vi } from 'vitest'

export type Call = { method: string; path: string; body?: unknown }

export const json = (body: unknown, status = 200) =>
  new Response(status === 204 ? null : JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })

export const problem = (status: number, title: string, extra: Record<string, unknown> = {}) =>
  new Response(JSON.stringify({ title, status, ...extra }), {
    status,
    headers: { 'Content-Type': 'application/problem+json' },
  })

/**
 * Replaces `fetch` with a stub. The handler gets each call (path without the `/api/v1` prefix,
 * query string included) and returns a `Response`, a plain value (sent as JSON), or `undefined`
 * (answered with 404). Returns the list of calls made so far.
 */
export function stubApi(handler: (call: Call) => unknown): Call[] {
  const calls: Call[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      const call: Call = {
        method: init?.method ?? 'GET',
        path: String(url).replace('/api/v1', ''),
        body: typeof init?.body === 'string' ? JSON.parse(init.body) : undefined,
      }
      calls.push(call)
      const answer = handler(call)
      if (answer instanceof Response) return answer
      if (answer === undefined) return problem(404, 'Not found')
      return json(answer)
    }),
  )
  return calls
}

export const STATUS = {
  ai: {
    provider: 'openai',
    status: 'working',
    message: null,
    checked_at: null,
  },
  checklist: {
    key_ok: true,
    resume_uploaded: true,
    profile_confirmed: true,
    preferences_saved: true,
    rules_approved: true,
    searched_once: false,
  },
  budget: { cap_usd: '25.00', spent_usd: '0', period: '2026-11' },
}
