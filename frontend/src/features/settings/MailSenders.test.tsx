import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it } from 'vitest'
import { type Call, problem, stubApi } from '@/test/api'
import { MailSenders } from './MailSenders'

type Sender = { id: string; address: string; site: string; built_in: boolean; enabled: boolean }

const BUILT_IN: Sender[] = [
  { id: 's1', address: 'jobalerts-noreply@linkedin.com', site: 'linkedin', built_in: true, enabled: true },
  { id: 's2', address: 'jobs@linkedin.com', site: 'linkedin', built_in: true, enabled: true },
  { id: 's3', address: 'naukrialerts@naukri.com', site: 'naukri', built_in: true, enabled: true },
]

let senders: Sender[]
let calls: Call[]

beforeEach(() => {
  senders = BUILT_IN.map((s) => ({ ...s }))
  calls = stubApi((call) => {
    if (call.method === 'GET' && call.path === '/mail/senders') return { items: senders }
    if (call.method === 'PATCH' && call.path.startsWith('/mail/senders/')) {
      const sender = senders.find((s) => call.path.endsWith(s.id)) as Sender
      sender.enabled = (call.body as { enabled: boolean }).enabled
      return sender
    }
    if (call.method === 'POST' && call.path === '/mail/senders') {
      const address = (call.body as { address: string }).address.trim().toLowerCase()
      if (senders.some((s) => s.address === address))
        return problem(409, 'Conflict', {
          detail: `${address} is already on the list.`,
          reason: 'sender_exists',
        })
      const added = { id: `n${senders.length}`, address, site: 'other', built_in: false, enabled: true }
      senders = [...senders, added]
      return new Response(JSON.stringify(added), { status: 201 })
    }
    if (call.method === 'DELETE' && call.path.startsWith('/mail/senders/')) {
      senders = senders.filter((s) => !call.path.endsWith(s.id))
      return new Response(null, { status: 204 })
    }
    return undefined
  })
})

function renderSenders() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <MailSenders />
    </QueryClientProvider>,
  )
}

describe('MailSenders', () => {
  it('US4 AS1 list by site with switches', async () => {
    renderSenders()

    const linkedin = await screen.findByRole('group', { name: 'LinkedIn' })
    expect(within(linkedin).getByText('jobalerts-noreply@linkedin.com')).toBeInTheDocument()
    expect(within(linkedin).getByText('jobs@linkedin.com')).toBeInTheDocument()
    expect(within(linkedin).getByRole('switch', { name: 'Read LinkedIn alerts' })).toBeChecked()
    const naukri = screen.getByRole('group', { name: 'Naukri' })
    expect(within(naukri).getByRole('switch', { name: 'Read Naukri alerts' })).toBeChecked()
  })

  it('US4 AS3 a site is switched off, and back on, for all its addresses', async () => {
    const user = userEvent.setup()
    renderSenders()

    await user.click(await screen.findByRole('switch', { name: 'Read LinkedIn alerts' }))

    await waitFor(() => expect(screen.getByRole('switch', { name: 'Read LinkedIn alerts' })).not.toBeChecked())
    const patches = calls.filter((c) => c.method === 'PATCH')
    expect(patches.map((c) => c.path).sort()).toEqual(['/mail/senders/s1', '/mail/senders/s2'])
    expect(patches.every((c) => (c.body as { enabled: boolean }).enabled === false)).toBe(true)
    expect(screen.getByRole('switch', { name: 'Read Naukri alerts' })).toBeChecked()
  })

  it('US4 AS3 switching a site off and on again reads the list each time', async () => {
    const user = userEvent.setup()
    renderSenders()

    await user.click(await screen.findByRole('switch', { name: 'Read LinkedIn alerts' }))
    await waitFor(() =>
      expect(screen.getByRole('switch', { name: 'Read LinkedIn alerts' })).not.toBeChecked(),
    )
    expect(within(screen.getByRole('group', { name: 'LinkedIn' })).getByText('Off')).toBeInTheDocument()
    await user.click(screen.getByRole('switch', { name: 'Read LinkedIn alerts' }))

    await waitFor(() =>
      expect(screen.getByRole('switch', { name: 'Read LinkedIn alerts' })).toBeChecked(),
    )
  })

  it('a switch where one address fails shows the site as partly on and says so', async () => {
    const user = userEvent.setup()
    calls = stubApi((call) => {
      if (call.method === 'GET' && call.path === '/mail/senders') return { items: senders }
      if (call.method === 'PATCH' && call.path === '/mail/senders/s2')
        return problem(500, 'Server error')
      if (call.method === 'PATCH') {
        const sender = senders.find((s) => call.path.endsWith(s.id)) as Sender
        sender.enabled = (call.body as { enabled: boolean }).enabled
        return sender
      }
      return undefined
    })
    renderSenders()

    await user.click(await screen.findByRole('switch', { name: 'Read LinkedIn alerts' }))

    expect(await screen.findByText(/1 of 2 addresses could not be changed/)).toBeInTheDocument()
    const linkedin = screen.getByRole('group', { name: 'LinkedIn' })
    await waitFor(() => expect(within(linkedin).getByText('Partly on')).toBeInTheDocument())
  })

  it('a failed removal says so next to the list, not under the add field', async () => {
    const user = userEvent.setup()
    senders = [
      ...senders,
      { id: 'n9', address: 'digest@board.example', site: 'other', built_in: false, enabled: true },
    ]
    calls = stubApi((call) => {
      if (call.method === 'GET') return { items: senders }
      return problem(500, 'Server error', { detail: 'Could not remove it.' })
    })
    renderSenders()

    await user.click(await screen.findByRole('button', { name: 'Remove digest@board.example' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Could not remove it.')
    expect(screen.getByText('digest@board.example')).toBeInTheDocument()
  })

  it('addresses the server would refuse are refused here too', async () => {
    const user = userEvent.setup()
    renderSenders()
    const field = await screen.findByLabelText('Sender address')

    for (const bad of ['-a@b.co', 'a"b@x.com', 'a@b..com', 'a@b_c.com']) {
      await user.clear(field)
      await user.type(field, bad)
      await user.click(screen.getByRole('button', { name: 'Add sender' }))
      expect(await screen.findByRole('alert')).toHaveTextContent(/plain email address/i)
    }
    expect(calls.some((c) => c.method === 'POST')).toBe(false)
  })

  it('US4 AS2 add a sender', async () => {
    const user = userEvent.setup()
    renderSenders()

    await user.type(await screen.findByLabelText('Sender address'), 'Digest@Board.example')
    await user.click(screen.getByRole('button', { name: 'Add sender' }))

    const own = await screen.findByRole('group', { name: 'Senders you added' })
    expect(within(own).getByText('digest@board.example')).toBeInTheDocument()
    expect(screen.getByLabelText('Sender address')).toHaveValue('')
  })

  it('a sender that is already listed says so', async () => {
    const user = userEvent.setup()
    renderSenders()

    await user.type(await screen.findByLabelText('Sender address'), 'jobs@linkedin.com')
    await user.click(screen.getByRole('button', { name: 'Add sender' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('jobs@linkedin.com is already on the list.')
  })

  it('built-in cannot be removed, an added sender can', async () => {
    const user = userEvent.setup()
    senders = [
      ...senders,
      { id: 'n9', address: 'digest@board.example', site: 'other', built_in: false, enabled: true },
    ]
    renderSenders()

    const own = await screen.findByRole('group', { name: 'Senders you added' })
    const linkedin = screen.getByRole('group', { name: 'LinkedIn' })
    expect(within(linkedin).queryByRole('button', { name: /remove/i })).not.toBeInTheDocument()

    await user.click(within(own).getByRole('button', { name: 'Remove digest@board.example' }))

    await waitFor(() =>
      expect(screen.queryByRole('group', { name: 'Senders you added' })).not.toBeInTheDocument(),
    )
    expect(calls.some((c) => c.method === 'DELETE' && c.path === '/mail/senders/n9')).toBe(true)
  })

  it('an address that is not an email is refused before anything is sent', async () => {
    const user = userEvent.setup()
    renderSenders()

    await user.type(await screen.findByLabelText('Sender address'), 'not an address')
    await user.click(screen.getByRole('button', { name: 'Add sender' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/email address/i)
    expect(calls.some((c) => c.method === 'POST')).toBe(false)
  })
})
