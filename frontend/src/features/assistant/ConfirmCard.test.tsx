import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
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
