import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it } from 'vitest'
import { type Call, problem, stubApi } from '@/test/api'
import { AiSection } from './AiSection'

const KEY = 'sk-test-0123456789abcdefghij'

type Ai = { provider: string; status: string; message: string | null; checked_at: string | null; key_source: string }

let ai: Ai
let calls: Call[]

function status() {
  return {
    ai,
    checklist: {
      key_ok: ai.status === 'working',
      resume_uploaded: true,
      profile_confirmed: true,
      preferences_saved: true,
      rules_approved: true,
      searched_once: false,
    },
  }
}

beforeEach(() => {
  ai = { provider: 'openai', status: 'missing', message: null, checked_at: null, key_source: 'none' }
  calls = stubApi((call) => {
    if (call.method === 'GET' && call.path === '/status') return status()
    if (call.method === 'PUT' && call.path === '/settings/ai-key') {
      const key = (call.body as { key: string }).key
      if (key.length < 20)
        return problem(422, 'Unprocessable', {
          detail: 'A key is 20 to 300 characters with no spaces.',
          reason: 'invalid_key',
          errors: [
            {
              field: 'key',
              message: 'A key is 20 to 300 characters with no spaces.',
            },
          ],
        })
      ai = { ...ai, key_source: 'page', status: 'unknown' }
      return new Response(JSON.stringify({ key_source: 'page', status: 'unknown' }), { status: 202 })
    }
    if (call.method === 'DELETE' && call.path === '/settings/ai-key') {
      ai = { ...ai, key_source: 'none', status: 'missing' }
      return new Response(null, { status: 204 })
    }
    if (call.method === 'POST' && call.path === '/status/ai/check') return { status: 'queued' }
    return undefined
  })
})

function renderSection() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  render(
    <QueryClientProvider client={client}>
      <AiSection />
    </QueryClientProvider>,
  )
  return client
}

describe('AiSection', () => {
  it('US6 AS2 saves a key typed on the page, then it is checked', async () => {
    const user = userEvent.setup()
    renderSection()

    expect(await screen.findByText('Missing')).toBeInTheDocument()
    await user.type(screen.getByLabelText('OpenAI API key'), KEY)
    await user.click(screen.getByRole('button', { name: 'Save key' }))

    await waitFor(() =>
      expect(calls.some((c) => c.method === 'PUT' && (c.body as { key: string }).key === KEY)).toBe(
        true,
      ),
    )
    expect(await screen.findByRole('status', { name: 'Key result' })).toHaveTextContent(
      'Saved. Checking the key…',
    )
    expect(await screen.findByText(/saved on this page/i)).toBeInTheDocument()
  })

  it('US6 AS3 the key is never shown again after saving', async () => {
    const user = userEvent.setup()
    renderSection()

    const field = await screen.findByLabelText('OpenAI API key')
    expect(field).toHaveAttribute('type', 'password')
    await user.type(field, KEY)
    await user.click(screen.getByRole('button', { name: 'Save key' }))

    await screen.findByRole('status', { name: 'Key result' })
    expect(screen.getByLabelText('Replace the key')).toHaveValue('')
    expect(document.body.innerHTML).not.toContain(KEY)
  })

  it('US6 AS4 a key from .env cannot be changed here and says so', async () => {
    ai = { ...ai, status: 'working', key_source: 'env' }
    renderSection()

    expect(await screen.findByText('Working')).toBeInTheDocument()
    expect(screen.getByText(/OPENAI_API_KEY in \.env/)).toBeInTheDocument()
    expect(screen.queryByLabelText('OpenAI API key')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /remove/i })).not.toBeInTheDocument()
  })

  it('a key of the wrong shape is refused with the reason', async () => {
    const user = userEvent.setup()
    renderSection()

    await user.type(await screen.findByLabelText('OpenAI API key'), 'short')
    await user.click(screen.getByRole('button', { name: 'Save key' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('20 to 300 characters')
  })

  it('US6 AS3 a saved key can be removed after a confirmation', async () => {
    ai = { ...ai, status: 'working', key_source: 'page' }
    const user = userEvent.setup()
    renderSection()

    await user.click(await screen.findByRole('button', { name: 'Remove key' }))
    expect(calls.some((c) => c.method === 'DELETE')).toBe(false) // not yet: it asks first
    await user.click(screen.getByRole('button', { name: 'Yes, remove the key' }))

    await waitFor(() => expect(calls.some((c) => c.method === 'DELETE')).toBe(true))
    expect(await screen.findByText('Missing')).toBeInTheDocument()
  })

  it('test_US2_AS5_ai_key_button_says_test_key', async () => {
    ai = { ...ai, status: 'rejected', key_source: 'page' }
    const user = userEvent.setup()
    renderSection()

    await user.click(await screen.findByRole('button', { name: 'Test key' }))

    await waitFor(() =>
      expect(calls.some((c) => c.method === 'POST' && c.path === '/status/ai/check')).toBe(true),
    )
    expect(screen.getByText('Rejected by the provider')).toBeInTheDocument()
  })

  it('out of credit shows the provider message', async () => {
    ai = {
      ...ai,
      status: 'out_of_credit',
      key_source: 'page',
      message: 'You exceeded your quota.',
    }
    renderSection()

    expect(await screen.findByText('You exceeded your quota.')).toBeInTheDocument()
  })
})

describe('AiSection: the key heartbeat', () => {
  it('a working key shows a moving heartbeat', async () => {
    ai = { ...ai, status: 'working', key_source: 'page' }
    renderSection()

    const beat = await screen.findByRole('img', {
      name: 'AI key working: heartbeat',
    })
    expect(beat).toHaveClass('ht-ecg-live')
  })

  it('a key being checked beats too, a missing or rejected key is a flat line', async () => {
    ai = { ...ai, status: 'unknown', key_source: 'page' }
    renderSection()
    expect(
      await screen.findByRole('img', {
        name: 'AI key being checked: heartbeat',
      }),
    ).toHaveClass('ht-ecg-live')
  })

  it('a missing key is a flat line', async () => {
    renderSection()

    const flat = await screen.findByRole('img', {
      name: 'AI key missing: flat line',
    })
    expect(flat).not.toHaveClass('ht-ecg-live')
  })
})

describe('AiSection: review fixes', () => {
  it('the confirmation takes the focus, and Cancel gives it back to Remove key', async () => {
    ai = { ...ai, status: 'working', key_source: 'page' }
    const user = userEvent.setup()
    renderSection()

    await user.click(await screen.findByRole('button', { name: 'Remove key' }))
    expect(screen.getByRole('button', { name: 'Yes, remove the key' })).toHaveFocus()
    await user.click(screen.getByRole('button', { name: 'Cancel' }))

    expect(screen.getByRole('button', { name: 'Remove key' })).toHaveFocus()
  })

  it('the saved note goes once the check has answered', async () => {
    const user = userEvent.setup()
    renderSection()

    await user.type(await screen.findByLabelText('OpenAI API key'), KEY)
    await user.click(screen.getByRole('button', { name: 'Save key' }))
    await screen.findByRole('status', { name: 'Key result' })
    ai = { ...ai, status: 'working' }
    await user.click(screen.getByRole('button', { name: 'Test key' }))

    // the answer is announced in the same status line that said "Checking"
    await waitFor(() =>
      expect(screen.getByRole('status', { name: 'Key result' })).toHaveTextContent(
        'Saved. The key works.',
      ),
    )
  })

  it('after Remove, the focus goes to the key field', async () => {
    ai = { ...ai, status: 'working', key_source: 'page' }
    const user = userEvent.setup()
    renderSection()

    await user.click(await screen.findByRole('button', { name: 'Remove key' }))
    await user.click(screen.getByRole('button', { name: 'Yes, remove the key' }))

    await waitFor(() => expect(screen.getByLabelText('OpenAI API key')).toHaveFocus())
  })

  it('the saved key is not kept in memory by the save request', async () => {
    const user = userEvent.setup()
    const client = renderSection()

    await user.type(await screen.findByLabelText('OpenAI API key'), KEY)
    await user.click(screen.getByRole('button', { name: 'Save key' }))
    await screen.findByText('Saved. Checking the key…')

    const kept = client
      .getMutationCache()
      .getAll()
      .map((m) => JSON.stringify(m.state.variables))
    expect(kept.join(' ')).not.toContain(KEY)
  })
})
