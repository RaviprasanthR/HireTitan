import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { RefCard } from './RefCard'

function json(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })
}

function show() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <RefCard refText="draft:d1" />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

const WRITING = {
  ref: 'draft:d1',
  kind: 'draft',
  title: 'Email',
  subtitle: 'For Dana · writing…',
  lines: [],
  link: '/jobs/j1',
}
const READY = {
  ...WRITING,
  subtitle: 'For Dana',
  lines: ['Subject: Backend role', 'Hi Dana, glad to connect.'],
}

describe('RefCard: a draft', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('002m_a_draft_being_written_shows_progress_and_no_copy_yet', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => json(WRITING)),
    )
    show()

    expect(await screen.findByText('For Dana · writing…')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Copy' })).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Open the job' })).toHaveAttribute('href', '/jobs/j1')
  })

  it('002m_the_card_fills_in_by_itself_when_the_draft_is_ready', async () => {
    let calls = 0
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => json(++calls < 2 ? WRITING : READY)),
    )
    show()

    expect(await screen.findByText(/Hi Dana, glad to connect/, {}, { timeout: 5000 })).toBeVisible()
    expect(screen.getByRole('button', { name: 'Copy' })).toBeVisible()
  }, 10_000)

  it('002m_copy_puts_the_whole_text_on_the_clipboard', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => json(READY)),
    )
    const user = userEvent.setup()
    show()
    const writeText = vi.spyOn(navigator.clipboard, 'writeText')

    await user.click(await screen.findByRole('button', { name: 'Copy' }))

    await waitFor(() =>
      expect(writeText).toHaveBeenCalledWith('Subject: Backend role\n\nHi Dana, glad to connect.'),
    )
    expect(await screen.findByRole('button', { name: 'Copied' })).toBeVisible()
  })
})
