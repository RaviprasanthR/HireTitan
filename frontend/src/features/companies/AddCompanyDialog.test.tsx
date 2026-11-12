import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { problem, stubApi, type Call } from '@/test/api'
import { AddCompanyDialog } from './AddCompanyDialog'

const CREATED = {
  id: 'n',
  origin: 'user',
  name: 'Newco',
  city: null,
  website: null,
  careers_url: 'https://newco.example.com/careers',
  ats_vendor: null,
  board_id: null,
  resolution: 'unresolved',
  board_status: 'unresolved',
  hidden: false,
  user_modified: false,
  last_checked_at: null,
  last_check_result: null,
  last_check_error: null,
}

function renderDialog(handler: (call: Call) => unknown) {
  const calls = stubApi(handler)
  const onClose = vi.fn()
  render(
    <QueryClientProvider client={new QueryClient()}>
      <AddCompanyDialog onClose={onClose} />
    </QueryClientProvider>,
  )
  return { calls, onClose }
}

async function fillAndSubmit(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText('Company name'), 'Newco')
  await user.type(screen.getByLabelText('Careers page link'), 'https://newco.example.com/careers')
  await user.click(screen.getByRole('button', { name: 'Find job board' }))
}

afterEach(() => vi.unstubAllGlobals())

describe('AddCompanyDialog', () => {
  it('US3_AS2_confirm_suggested_board', async () => {
    const user = userEvent.setup()
    const { calls, onClose } = renderDialog((call) => {
      if (call.method === 'POST' && call.path === '/companies') return CREATED
      if (call.path === '/companies/n/discovery')
        return {
          status: 'found',
          suggestion: { ats_vendor: 'lever', board_id: 'newco', supported: true, live_jobs: 12 },
        }
      if (call.path === '/companies/n/discovery/confirm')
        return { ...CREATED, ats_vendor: 'lever', board_id: 'newco', board_status: 'board' }
      return undefined
    })

    await fillAndSubmit(user)

    expect(await screen.findByText(/lever/i)).toBeInTheDocument()
    expect(screen.getByText(/12 open jobs/)).toBeInTheDocument()
    expect(calls.some((c) => c.path.endsWith('/confirm'))).toBe(false) // only after the click
    await user.click(screen.getByRole('button', { name: 'Yes, use this board' }))

    expect(await screen.findByText(/will be read through lever/i)).toBeInTheDocument()
    expect(calls.some((c) => c.path === '/companies/n/discovery/confirm')).toBe(true)
    await user.click(screen.getByRole('button', { name: 'Done' }))
    expect(onClose).toHaveBeenCalled()
  })

  it('US3_AS2_not_this_one_reads_the_careers_page', async () => {
    const user = userEvent.setup()
    const { calls } = renderDialog((call) => {
      if (call.method === 'POST' && call.path === '/companies') return CREATED
      if (call.path === '/companies/n/discovery')
        return {
          status: 'found',
          suggestion: { ats_vendor: 'lever', board_id: 'other', supported: true, live_jobs: 3 },
        }
      if (call.path === '/companies/n/discovery/reject')
        return { ...CREATED, resolution: 'careers_page', board_status: 'careers_page' }
      return undefined
    })

    await fillAndSubmit(user)
    await user.click(await screen.findByRole('button', { name: 'Not this one' }))

    expect(await screen.findByText(/careers page will be read/i)).toBeInTheDocument()
    await waitFor(() =>
      expect(calls.some((c) => c.path === '/companies/n/discovery/reject')).toBe(true),
    )
  })

  it('no_board_found_still_keeps_the_company', async () => {
    const user = userEvent.setup()
    renderDialog((call) => {
      if (call.method === 'POST' && call.path === '/companies') return CREATED
      if (call.path === '/companies/n/discovery') return { status: 'none', suggestion: null }
      if (call.path === '/companies/n/discovery/reject')
        return { ...CREATED, resolution: 'careers_page', board_status: 'careers_page' }
      return undefined
    })

    await fillAndSubmit(user)

    expect(await screen.findByText(/no job board found/i)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Read the careers page' }))
    expect(await screen.findByText(/careers page will be read/i)).toBeInTheDocument()
  })

  it('shows_field_errors', async () => {
    const user = userEvent.setup()
    renderDialog((call) =>
      call.method === 'POST'
        ? problem(422, 'Invalid', {
            errors: [
              { field: 'careers_url', message: 'The link must start with http:// or https://.' },
            ],
          })
        : undefined,
    )

    await fillAndSubmit(user)

    expect(await screen.findByText(/must start with http/)).toBeInTheDocument()
  })

  it('FR026 the form has a website field and sends it', async () => {
    const user = userEvent.setup()
    const { calls } = renderDialog((call) =>
      call.method === 'POST' && call.path === '/companies' ? CREATED : undefined,
    )

    await user.type(screen.getByLabelText('Website (optional)'), 'https://newco.example.com')
    await fillAndSubmit(user)

    await waitFor(() =>
      expect(calls.find((c) => c.method === 'POST' && c.path === '/companies')?.body).toMatchObject(
        { name: 'Newco', website: 'https://newco.example.com' },
      ),
    )
  })

  it('FR026 it is a square card over a blurred backdrop, and Escape closes it', async () => {
    const user = userEvent.setup()
    const { onClose } = renderDialog(() => undefined)
    const dialog = screen.getByRole('dialog', { name: 'Add a company' })

    expect(dialog).toHaveAttribute('aria-modal', 'true')
    expect(dialog).toHaveClass('aspect-square')
    expect(dialog.parentElement).toHaveClass('backdrop-blur-sm')

    await user.keyboard('{Escape}')

    expect(onClose).toHaveBeenCalled()
  })

  it('FR026 a click on the blurred backdrop closes it, a click on the card does not', async () => {
    const user = userEvent.setup()
    const { onClose } = renderDialog(() => undefined)
    const dialog = screen.getByRole('dialog', { name: 'Add a company' })

    await user.click(screen.getByLabelText('Company name'))
    expect(onClose).not.toHaveBeenCalled()
    await user.click(dialog.parentElement as HTMLElement)

    expect(onClose).toHaveBeenCalled()
  })

  it('review: focus moves into the card on open and Tab stays inside it', async () => {
    const user = userEvent.setup()
    renderDialog(() => undefined)
    const dialog = screen.getByRole('dialog', { name: 'Add a company' })

    expect(screen.getByLabelText('Company name')).toHaveFocus()
    for (let i = 0; i < 12; i++) {
      await user.tab()
      expect(dialog).toContainElement(document.activeElement as HTMLElement)
    }
    await user.tab({ shift: true })
    expect(dialog).toContainElement(document.activeElement as HTMLElement)
  })

  it('review: focus goes back to the button that opened it', () => {
    const opener = document.createElement('button')
    document.body.append(opener)
    opener.focus()
    const calls = stubApi(() => undefined)
    expect(calls).toBeDefined()
    const { unmount } = render(
      <QueryClientProvider client={new QueryClient()}>
        <AddCompanyDialog onClose={() => undefined} />
      </QueryClientProvider>,
    )

    unmount()

    expect(opener).toHaveFocus()
    opener.remove()
  })
})
