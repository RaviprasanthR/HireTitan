import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { type Call, STATUS, stubApi } from '@/test/api'
import { SettingsPage } from './SettingsPage'

function renderPage(keyStatus = 'working') {
  const calls: Call[] = stubApi((call) => {
    if (call.path === '/status') return { ...STATUS, ai: { ...STATUS.ai, status: keyStatus } }
    if (call.method === 'POST' && call.path === '/status/ai/check') return { status: 'queued' }
    return undefined
  })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <SettingsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
  return calls
}

afterEach(() => vi.unstubAllGlobals())

describe('SettingsPage', () => {
  it('FR020 settings shows key status and delete all only', async () => {
    const calls = renderPage()

    expect(await screen.findByText('Found, working')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Check again' })).toBeInTheDocument()
    expect(screen.getAllByRole('heading', { level: 2 }).map((h) => h.textContent)).toEqual([
      'AI key',
      expect.stringMatching(/delete all my data/i),
    ])
    expect(screen.queryByText(/budget|cap|spent|cost/i)).not.toBeInTheDocument() // SC003
    expect(screen.queryByRole('table')).not.toBeInTheDocument() // no models table
    expect(calls.some((c) => c.path === '/settings')).toBe(false) // read from /status
  })

  it('shows_a_missing_key_with_how_to_fix_it', async () => {
    renderPage('missing')

    expect(await screen.findByText('Missing')).toBeInTheDocument()
    expect(screen.getByText(/Add OPENAI_API_KEY to .env/)).toBeInTheDocument()
  })

  it('check_again_asks_the_server_to_recheck', async () => {
    const user = userEvent.setup()
    const calls = renderPage()

    await user.click(await screen.findByRole('button', { name: 'Check again' }))

    await waitFor(() =>
      expect(calls.some((c) => c.method === 'POST' && c.path === '/status/ai/check')).toBe(true),
    )
  })

  it('never_shows_a_key_field', async () => {
    renderPage()
    await screen.findByText('Found, working')

    expect(screen.queryByLabelText(/api key/i)).not.toBeInTheDocument()
  })
})
