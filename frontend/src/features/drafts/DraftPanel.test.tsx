import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { type Call, problem, stubApi } from '@/test/api'
import { ActOnJob } from './ActOnJob'

const CONTACT = {
  contact_id: 'c1',
  name: 'Asha Rao',
  role: 'Talent Partner',
  kind: 'recruiter',
}

function draft(over: Record<string, unknown> = {}) {
  return {
    id: 'd1',
    kind: 'connection_request',
    recipient: {
      contact_id: 'c1',
      name: 'Asha Rao',
      role: 'Talent Partner',
      kind: 'recruiter',
    },
    status: 'ready',
    paused_reason: null,
    text: 'Hi Asha, I build Python APIs and would like to connect.',
    source: 'ai',
    edited: false,
    cited_facts: [{ id: 'skill:python', text: 'Python' }],
    failure_reason: null,
    chars: 55,
    over_limit: false,
    updated_at: '2026-11-17T09:00:00Z',
    ...over,
  }
}

type Setup = {
  contacts?: unknown[]
  drafts?: unknown[]
  signals?: unknown[]
  create?: unknown
}

function renderPanel({ contacts = [CONTACT], drafts = [], signals = [], create }: Setup = {}) {
  const calls = stubApi((call: Call) => {
    if (call.path === '/jobs/j1/recipients')
      return {
        contacts,
        kinds: ['recruiter', 'hiring_manager', 'engineer', 'other'],
      }
    if (call.path === '/jobs/j1/drafts' && call.method === 'GET')
      return { drafts, injection_signals: signals }
    if (call.path === '/jobs/j1/drafts' && call.method === 'POST')
      return create ?? { id: 'd1', status: 'writing' }
    if (call.path.startsWith('/drafts/') && call.method === 'PUT') return draft({ edited: true })
    if (call.path.startsWith('/drafts/') && call.method === 'DELETE')
      return new Response(null, { status: 204 })
    return undefined
  })
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <MemoryRouter>
        <ActOnJob jobId="j1" title="Backend Engineer" />
      </MemoryRouter>
    </QueryClientProvider>,
  )
  return calls
}

afterEach(() => vi.unstubAllGlobals())

describe('DraftPanel', () => {
  it('US2 AS1 pick a contact or someone else', async () => {
    const user = userEvent.setup()
    const calls = renderPanel()
    await user.click(screen.getByRole('button', { name: 'Connection request' }))

    const who = await screen.findByRole('combobox', { name: 'Who is it for' })
    await user.selectOptions(who, 'c1')
    await user.click(screen.getByRole('button', { name: 'Write' }))
    await waitFor(() =>
      expect(calls.find((c) => c.method === 'POST')?.body).toMatchObject({
        kind: 'connection_request',
        recipient: { contact_id: 'c1' },
        regenerate: false,
      }),
    )

    await user.selectOptions(who, '__typed__')
    await user.type(screen.getByLabelText('Name'), 'Dev Patel')
    await user.type(screen.getByLabelText('Role'), 'Engineering Manager')
    await user.click(screen.getByRole('button', { name: 'Write' }))
    await waitFor(() =>
      expect(calls.filter((c) => c.method === 'POST')[1]?.body).toMatchObject({
        recipient: { name: 'Dev Patel', role: 'Engineering Manager' },
      }),
    )
  })

  it('US2 AS1 with no contacts only a typed recipient is offered', async () => {
    const user = userEvent.setup()
    renderPanel({ contacts: [] })
    await user.click(screen.getByRole('button', { name: 'Connection request' }))

    expect(await screen.findByLabelText('Name')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Write' })).toBeDisabled()
  })

  it('US2 AS2 live count and warning above 200', async () => {
    const user = userEvent.setup()
    renderPanel({ drafts: [draft()] })
    await user.click(screen.getByRole('button', { name: 'Connection request' }))

    const box = await screen.findByRole('textbox', {
      name: 'Draft for Asha Rao',
    })
    expect(screen.getByText(/^55 \/ 200$/)).toBeInTheDocument()
    await user.clear(box)
    await user.click(box)
    await user.paste('x'.repeat(230))
    expect(screen.getByText(/230 \/ 200/)).toHaveClass('text-danger')
    expect(screen.getByText(/limits a connection request to 200/)).toBeInTheDocument()
  })

  it('US2 AS3 shows the profile facts used', async () => {
    const user = userEvent.setup()
    renderPanel({ drafts: [draft()] })
    await user.click(screen.getByRole('button', { name: 'Connection request' }))

    expect(await screen.findByText('From your profile')).toBeInTheDocument()
    expect(screen.getByRole('listitem')).toHaveTextContent('Python')
  })

  it('FR004 says it is never sent', async () => {
    const user = userEvent.setup()
    renderPanel({ drafts: [draft()] })
    await user.click(screen.getByRole('button', { name: 'Connection request' }))

    expect(
      await screen.findByText('HireTitan never sends this. Copy it and send it yourself.'),
    ).toBeInTheDocument()
  })

  it('US2 AS6 out of credit shows the reason', async () => {
    const user = userEvent.setup()
    renderPanel({
      drafts: [
        draft({
          status: 'writing',
          text: null,
          paused_reason: 'Your AI account is out of credit.',
        }),
      ],
    })
    await user.click(screen.getByRole('button', { name: 'Connection request' }))

    expect(await screen.findByRole('status')).toHaveTextContent('Writing…')
    expect(screen.getByText('Your AI account is out of credit.')).toBeInTheDocument()
  })

  it('US2 AS6 a refused start shows the provider reason', async () => {
    const user = userEvent.setup()
    renderPanel({
      create: problem(409, 'Conflict', {
        detail: 'Your AI account is out of credit.',
      }),
    })
    await user.click(screen.getByRole('button', { name: 'Connection request' }))
    await user.selectOptions(await screen.findByRole('combobox', { name: 'Who is it for' }), 'c1')
    await user.click(screen.getByRole('button', { name: 'Write' }))

    expect(await screen.findByRole('alert')).toBeInTheDocument()
  })

  it('US2 AS7 last draft shown again; write again asks when edited', async () => {
    const user = userEvent.setup()
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
    const calls = renderPanel({ drafts: [draft({ edited: true })] })
    await user.click(screen.getByRole('button', { name: 'Connection request' }))

    expect(await screen.findByDisplayValue(/Hi Asha, I build Python APIs/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Write again' }))
    expect(confirm).toHaveBeenCalled()
    expect(calls.some((c) => c.method === 'POST')).toBe(false)

    confirm.mockReturnValue(true)
    await user.click(screen.getByRole('button', { name: 'Write again' }))
    await waitFor(() =>
      expect(calls.find((c) => c.method === 'POST')?.body).toMatchObject({
        regenerate: true,
      }),
    )
    confirm.mockRestore()
  })

  it('EC11 copy falls back to selecting the text', async () => {
    const user = userEvent.setup()
    renderPanel({ drafts: [draft()] })
    await user.click(screen.getByRole('button', { name: 'Connection request' }))
    await screen.findByRole('textbox', { name: 'Draft for Asha Rao' })
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText: () => Promise.reject(new Error('denied')) },
    })

    await user.click(screen.getByRole('button', { name: 'Copy' }))

    expect(await screen.findByText('Press Ctrl+C to copy')).toBeInTheDocument()
  })

  it('FR006 EC12 shows the injection notice', async () => {
    const user = userEvent.setup()
    renderPanel({
      drafts: [draft()],
      signals: [{ rule_id: 'ai_instruction', severity: 'high', excerpt: 'ignore' }],
    })
    await user.click(screen.getByRole('button', { name: 'Connection request' }))

    expect(await screen.findByRole('note')).toHaveTextContent(
      'This posting contains text that looks like instructions to an AI. HireTitan ignored it.',
    )
  })

  it('US3 AS1 writes a referral for the chosen recipient', async () => {
    const user = userEvent.setup()
    const calls = renderPanel()
    await user.click(screen.getByRole('button', { name: 'Referral message' }))
    await user.selectOptions(await screen.findByRole('combobox', { name: 'Who is it for' }), 'c1')
    await user.click(screen.getByRole('button', { name: 'Write' }))

    await waitFor(() =>
      expect(calls.find((c) => c.method === 'POST')?.body).toMatchObject({
        kind: 'referral_message',
      }),
    )
  })

  it('US3 AS3 edits kept and length shown', async () => {
    const user = userEvent.setup()
    const calls = renderPanel({
      drafts: [
        draft({
          kind: 'referral_message',
          text: 'Hi Asha,\n\nA longer message.',
        }),
      ],
    })
    await user.click(screen.getByRole('button', { name: 'Referral message' }))
    const box = await screen.findByRole('textbox', {
      name: 'Draft for Asha Rao',
    })
    expect(screen.getByText(/characters$/)).toBeInTheDocument()
    expect(screen.queryByText(/\/ 200/)).not.toBeInTheDocument()

    await user.click(box)
    await user.keyboard('{Control>}{End}{/Control} More.')
    await user.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() =>
      expect(calls.find((c) => c.method === 'PUT')?.body).toEqual({
        text: 'Hi Asha,\n\nA longer message. More.',
      }),
    )
  })

  it('FR009 delete removes a draft', async () => {
    const user = userEvent.setup()
    const calls = renderPanel({ drafts: [draft()] })
    await user.click(screen.getByRole('button', { name: 'Connection request' }))
    const card = (await screen.findByRole('textbox', { name: 'Draft for Asha Rao' })).closest('div')
    await user.click(within(card as HTMLElement).getByRole('button', { name: 'Delete' }))

    await waitFor(() => expect(calls.some((c) => c.method === 'DELETE')).toBe(true))
  })

  it('keeps typed text when the draft is read again', async () => {
    const user = userEvent.setup()
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    let reads = 0
    stubApi((call: Call) => {
      if (call.path === '/jobs/j1/recipients') return { contacts: [CONTACT], kinds: [] }
      if (call.path === '/jobs/j1/drafts' && call.method === 'GET') {
        reads += 1
        return {
          drafts: [draft({ updated_at: `2026-11-17T09:00:0${reads}Z` })],
          injection_signals: [],
        }
      }
      return undefined
    })
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter>
          <ActOnJob jobId="j1" title="Backend Engineer" />
        </MemoryRouter>
      </QueryClientProvider>,
    )
    await user.click(screen.getByRole('button', { name: 'Connection request' }))
    const box = await screen.findByRole('textbox', { name: 'Draft for Asha Rao' })
    await user.type(box, ' Thanks!')

    await client.invalidateQueries({ queryKey: ['drafts'] })
    await waitFor(() => expect(reads).toBeGreaterThan(1))

    expect(screen.getByRole('textbox', { name: 'Draft for Asha Rao' })).toHaveValue(
      'Hi Asha, I build Python APIs and would like to connect. Thanks!',
    )
  })

  it('shows why writing again was refused', async () => {
    const user = userEvent.setup()
    renderPanel({ drafts: [draft()], create: problem(409, 'This draft is still being written.') })
    await user.click(screen.getByRole('button', { name: 'Connection request' }))
    const card = (await screen.findByRole('textbox', { name: 'Draft for Asha Rao' })).closest('div')
    await user.click(within(card as HTMLElement).getByRole('button', { name: 'Write again' }))

    expect(await within(card as HTMLElement).findByRole('alert')).toHaveTextContent(
      'This draft is still being written.',
    )
  })
})
