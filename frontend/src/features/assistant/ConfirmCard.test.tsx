import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '@/api/client'
import { ChangeNotice } from './ChangeNotice'
import { ConfirmCard } from './ConfirmCard'
import type { CardData } from './stream'

const later = new Date(Date.now() + 30 * 60_000).toISOString()

const card: CardData = {
  card_id: 'k1',
  summary: 'Mark as applied: Backend Engineer at Acme',
  items: [{ action: 'mark_applied_many', args: { jobs: ['job:1'], on: null }, editable: ['on'] }],
  expires_at: later,
  state: 'proposed',
}

describe('ConfirmCard', () => {
  it('US2_AS4_card_confirm_cancel_edit', async () => {
    const onConfirm = vi.fn(async () => {})
    const onCancel = vi.fn(async () => {})
    const user = userEvent.setup()
    render(<ConfirmCard card={card} onConfirm={onConfirm} onCancel={onCancel} />)

    expect(screen.getByText('Mark as applied: Backend Engineer at Acme')).toBeInTheDocument()
    await user.type(screen.getByLabelText('on'), '2026-11-20')
    await user.click(screen.getByRole('button', { name: 'Confirm' }))

    expect(onConfirm).toHaveBeenCalledWith('k1', [{ index: 0, args: { on: '2026-11-20' } }])
    expect(await screen.findByText('Done.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Confirm' })).not.toBeInTheDocument()

    render(
      <ConfirmCard card={{ ...card, card_id: 'k2' }} onConfirm={onConfirm} onCancel={onCancel} />,
    )
    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(onCancel).toHaveBeenCalledWith('k2')
    expect(await screen.findByText('Cancelled. Nothing changed.')).toBeInTheDocument()
  })

  it('EC02_stale_card_message', async () => {
    const onConfirm = vi.fn(async () => {
      throw new ApiError(409, {
        detail: 'Something changed since Mikasa proposed this, so it was not applied.',
        reason: 'stale',
      })
    })
    const user = userEvent.setup()
    render(<ConfirmCard card={card} onConfirm={onConfirm} onCancel={vi.fn()} />)

    await user.click(screen.getByRole('button', { name: 'Confirm' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Something changed')
    expect(screen.getByText(/expired/)).toBeInTheDocument()
  })

  it('an expired card cannot be confirmed', () => {
    render(
      <ConfirmCard card={{ ...card, state: 'expired' }} onConfirm={vi.fn()} onCancel={vi.fn()} />,
    )
    expect(screen.queryByRole('button', { name: 'Confirm' })).not.toBeInTheDocument()
  })
})

describe('ChangeNotice', () => {
  it('FR014_undo_notice', async () => {
    const onUndo = vi.fn(async () => {})
    const user = userEvent.setup()
    render(
      <ChangeNotice
        change={{
          change_id: 'c1',
          action: 'mark_applied',
          summary: 'Marked it.',
          undo_until: later,
        }}
        onUndo={onUndo}
      />,
    )

    await user.click(screen.getByRole('button', { name: 'Undo' }))

    expect(onUndo).toHaveBeenCalledWith('c1')
    await waitFor(() => expect(screen.getByText('Undone.')).toBeInTheDocument())
  })

  it('FR014_undo_refusal_is_shown', async () => {
    const onUndo = vi.fn(async () => {
      throw new Error('This item changed after that.')
    })
    const user = userEvent.setup()
    render(
      <ChangeNotice
        change={{
          change_id: 'c1',
          action: 'mark_applied',
          summary: 'Marked it.',
          undo_until: later,
        }}
        onUndo={onUndo}
      />,
    )
    await user.click(screen.getByRole('button', { name: 'Undo' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('This item changed after that.')
  })
})

describe('ConfirmCard: what a confirmed card made (US3)', () => {
  afterEach(() => vi.unstubAllGlobals())

  const reply = (body: Record<string, unknown>) =>
    vi.stubGlobal(
      'fetch',
      vi.fn(
        async () =>
          new Response(JSON.stringify(body), {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
          }),
      ),
    )

  const wrap = (node: React.ReactNode) => (
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter>{node}</MemoryRouter>
    </QueryClientProvider>
  )

  it('US3_AS1_draft_card_links_to_job', async () => {
    reply({
      ref: 'draft:d1',
      kind: 'draft',
      title: 'LinkedIn connection message',
      subtitle: 'For Hiring team',
      lines: [],
      link: '/jobs/j1',
    })
    const user = userEvent.setup()
    render(
      wrap(<ConfirmCard card={card} onConfirm={async () => ['draft:d1']} onCancel={vi.fn()} />),
    )

    await user.click(screen.getByRole('button', { name: 'Confirm' }))

    expect(await screen.findByText('LinkedIn connection message')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Open the job' })).toHaveAttribute('href', '/jobs/j1')
  })

  it('US3_AS2_resume_card_links_to_preview', async () => {
    reply({
      ref: 'tailored_resume:r1',
      kind: 'tailored_resume',
      title: 'Tailored resume',
      subtitle: 'Backend Engineer at Acme',
      lines: [],
      link: '/jobs/j1/resume',
    })
    const user = userEvent.setup()
    render(
      wrap(
        <ConfirmCard
          card={card}
          onConfirm={async () => ['tailored_resume:r1']}
          onCancel={vi.fn()}
        />,
      ),
    )

    await user.click(screen.getByRole('button', { name: 'Confirm' }))

    const link = await screen.findByRole('link', { name: /Tailored resume/ })
    expect(link).toHaveAttribute('href', '/jobs/j1/resume')
  })

  it('US3_a_reloaded_card_shows_what_it_made', async () => {
    reply({
      ref: 'draft:d1',
      kind: 'draft',
      title: 'Email',
      subtitle: 'For Dana',
      lines: ['Hi Dana'],
      link: '/jobs/j1',
    })
    render(
      wrap(
        <ConfirmCard
          card={{ ...card, state: 'applied', result: [{ refs: ['draft:d1'] }] }}
          onConfirm={vi.fn()}
          onCancel={vi.fn()}
        />,
      ),
    )

    expect(await screen.findByText('Hi Dana')).toBeInTheDocument()
  })
})
