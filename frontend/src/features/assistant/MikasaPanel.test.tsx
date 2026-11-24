import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { CONVERSATION_KEY, MikasaPanel } from './MikasaPanel'

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function sse(pieces: string[], hold?: Promise<void>) {
  const encoder = new TextEncoder()
  return new Response(
    new ReadableStream({
      async start(controller) {
        for (const piece of pieces) controller.enqueue(encoder.encode(piece))
        if (hold) await hold
        controller.close()
      },
    }),
    { status: 200, headers: { 'Content-Type': 'text/event-stream' } },
  )
}

let status: unknown
let stored: unknown[]
let turn: (init: RequestInit) => Response | Promise<Response>

function stubApi() {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init: RequestInit = {}) => {
      if (url.endsWith('/assistant/status')) return json(status)
      if (url.endsWith('/assistant/conversations') && init.method === 'POST')
        return json({ id: 'c1' }, 201)
      if (url.endsWith('/assistant/conversations')) return json([])
      if (url.endsWith('/messages')) return json(stored)
      if (url.endsWith('/turns')) return turn(init)
      return json({}, 404)
    }),
  )
}

function show(onClose = () => {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/companies']}>
        <main>The page</main>
        <MikasaPanel onClose={onClose} />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('MikasaPanel', () => {
  beforeEach(() => {
    localStorage.clear()
    status = { available: true, reason: null, provider_message: null }
    stored = []
    turn = () => sse([])
    stubApi()
  })
  afterEach(() => vi.unstubAllGlobals())

  it('US1_AS1_panel_opens_beside_page', async () => {
    show()
    expect(screen.getByRole('complementary', { name: 'Mikasa' })).toBeInTheDocument()
    expect(screen.getByText('The page')).toBeInTheDocument() // the page stays
    expect(await screen.findByText(/Ask me about your jobs/)).toBeInTheDocument()
  })

  it('FR022b_privacy_note_shown', () => {
    show()
    expect(
      screen.getByText(/What you type here is sent to your AI provider\. Contacts, notes/),
    ).toBeInTheDocument()
  })

  it('FR024_unavailable_message', async () => {
    status = { available: false, reason: 'out_of_credit', provider_message: 'Quota exceeded' }
    show()
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('out of credit')
    expect(alert).toHaveTextContent('Quota exceeded')
    expect(screen.getByRole('link', { name: 'Open Settings' })).toHaveAttribute('href', '/settings')
    expect(screen.getByLabelText('Message to Mikasa')).toBeDisabled()
  })

  it('US1_AS5_text_streams_and_stop', async () => {
    let release = () => {}
    const hold = new Promise<void>((resolve) => (release = resolve))
    let sent: RequestInit | undefined
    turn = (init) => {
      sent = init
      return sse(['event: text\ndata: {"delta": "Two jobs"}\n\n'], hold)
    }
    const user = userEvent.setup()
    show()
    await screen.findByText(/Ask me about your jobs/)

    await user.type(screen.getByLabelText('Message to Mikasa'), 'What did I apply to?{Enter}')

    expect(await screen.findByTestId('live-reply')).toHaveTextContent('Two jobs')
    expect(JSON.parse(String(sent?.body))).toEqual({
      text: 'What did I apply to?',
      page: '/companies',
    })
    expect(localStorage.getItem(CONVERSATION_KEY)).toBe('c1')
    await user.click(screen.getByRole('button', { name: 'Stop' }))
    release()
    await waitFor(() => expect(screen.queryByTestId('live-reply')).not.toBeInTheDocument())
  })

  it('FR021_posting_like_message_offered_to_paste', async () => {
    turn = () =>
      json(
        {
          detail: 'That looks like a job posting. Use Paste a job description.',
          reason: 'looks_like_posting',
        },
        422,
      )
    const user = userEvent.setup()
    show()
    await screen.findByText(/Ask me about your jobs/)
    const box = screen.getByLabelText('Message to Mikasa')

    await user.type(box, 'Responsibilities and requirements{Enter}')

    expect(await screen.findByRole('alert')).toHaveTextContent('Use Paste a job description')
    expect(box).toHaveValue('Responsibilities and requirements') // kept, nothing was sent
  })

  it('FR001_panel_on_every_page_keeps_conversation', async () => {
    localStorage.setItem(CONVERSATION_KEY, 'c9')
    stored = [
      {
        id: 'm1',
        seq: 1,
        author: 'person',
        text: 'Hello',
        status: 'complete',
        refs: [],
        signals: [],
        error: null,
        created_at: '',
      },
      {
        id: 'm2',
        seq: 2,
        author: 'mikasa',
        text: 'Hi there',
        status: 'complete',
        refs: [],
        signals: [],
        error: null,
        created_at: '',
      },
    ]
    const onClose = vi.fn()
    const user = userEvent.setup()
    show(onClose)

    expect(await screen.findByText('Hi there')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Close Mikasa' }))
    expect(onClose).toHaveBeenCalled()
    expect(localStorage.getItem(CONVERSATION_KEY)).toBe('c9')
  })

  it('counts characters and stops at 2,000', async () => {
    const user = userEvent.setup()
    show()
    await screen.findByText(/Ask me about your jobs/)
    const box = screen.getByLabelText('Message to Mikasa')
    await user.click(box)
    await user.paste('x'.repeat(2001))
    expect(screen.getByText('2001 / 2000')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled()
  })
})
