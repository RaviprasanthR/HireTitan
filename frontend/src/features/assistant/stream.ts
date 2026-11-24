import { ApiError, type Problem } from '@/api/client'

/** One event of Mikasa's reply stream (contracts/rest-api.md, "Turn stream"). */
export type TurnStreamEvent =
  | { event: 'text'; data: { delta: string } }
  | { event: 'ref'; data: { ref: string } }
  | { event: 'notice'; data: { kind: string; text: string } }
  | {
      event: 'error'
      data: { reason: string; message: string; provider_message: string | null }
    }
  | { event: 'done'; data: { message_id: string | null; status: string; text: string } }
  | { event: 'change'; data: ChangeData }
  | { event: 'card'; data: CardData }

/** A small change applied at once, with its Undo (FR-014). */
export type ChangeData = {
  change_id: string
  action: string
  summary?: string
  undo_until: string | null
  undone?: boolean
  invalidate?: string[][]
}

/** A risky change waiting for the person's confirmation (FR-010). */
export type CardData = {
  card_id: string
  summary: string
  items: { action: string; args: Record<string, unknown>; editable: string[] }[]
  expires_at: string
  state?: string
}

const KNOWN = new Set(['text', 'ref', 'notice', 'error', 'done', 'change', 'card'])

/** Server-sent event frames from text that may arrive in any size of piece. */
export function frameParser(onFrame: (event: string, data: string) => void) {
  let buffer = ''
  return (chunk: string) => {
    buffer += chunk.replace(/\r\n/g, '\n')
    let end = buffer.indexOf('\n\n')
    while (end !== -1) {
      const frame = buffer.slice(0, end)
      buffer = buffer.slice(end + 2)
      let event = 'message'
      const data: string[] = []
      for (const line of frame.split('\n')) {
        if (line.startsWith(':')) continue // a comment, e.g. the keep-alive ping
        if (line.startsWith('event:')) event = line.slice(6).trim()
        else if (line.startsWith('data:')) data.push(line.slice(5).replace(/^ /, ''))
      }
      if (data.length) onFrame(event, data.join('\n'))
      end = buffer.indexOf('\n\n')
    }
  }
}

/**
 * Send a message and read Mikasa's reply as it is written (FR-002). `EventSource` cannot POST,
 * so this reads the stream with `fetch`. Aborting `signal` stops the turn on the server.
 */
export async function streamTurn(
  conversationId: string,
  text: string,
  page: string,
  onEvent: (event: TurnStreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(`/api/v1/assistant/conversations/${conversationId}/turns`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify({ text, page }),
    signal,
  })
  if (!response.ok) {
    let problem: Problem = { title: response.statusText }
    try {
      problem = (await response.json()) as Problem
    } catch {
      // not JSON: keep the status text
    }
    throw new ApiError(response.status, problem)
  }
  if (!response.body) return
  const parse = frameParser((event, data) => {
    if (!KNOWN.has(event)) return
    try {
      onEvent({ event, data: JSON.parse(data) } as TurnStreamEvent)
    } catch {
      // a malformed frame is skipped; the final "done" carries the whole reply anyway
    }
  })
  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader()
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    parse(value)
  }
}
