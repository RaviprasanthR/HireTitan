import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { type Call, problem, stubApi } from '@/test/api'
import { GmailSection } from './GmailSection'

const REDIRECT = 'http://localhost:8000/api/v1/mail/google/callback'

type Connection = {
  state: 'not_connected' | 'connected' | 'needs_reconnect'
  address: string | null
  credentials_set: boolean
  credentials_from_environment: boolean
  redirect_uri: string
  last_check_started_at: string | null
  last_error: string | null
  window_hours: number
}

const base: Connection = {
  state: 'not_connected',
  address: null,
  credentials_set: false,
  credentials_from_environment: false,
  redirect_uri: REDIRECT,
  last_check_started_at: null,
  last_error: null,
  window_hours: 24,
}

let connection: Connection
let calls: Call[]
let assign: ReturnType<typeof vi.fn>

beforeEach(() => {
  connection = { ...base }
  assign = vi.fn()
  vi.stubGlobal('location', { ...window.location, assign })
  calls = stubApi((call) => {
    if (call.method === 'GET' && call.path === '/mail/connection') return connection
    if (call.method === 'PUT' && call.path === '/mail/credentials') {
      connection = { ...connection, credentials_set: true }
      return connection
    }
    if (call.method === 'POST' && call.path === '/mail/connect')
      return { authorize_url: 'https://accounts.example.invalid/auth?state=s' }
    if (call.method === 'DELETE' && call.path === '/mail/connection') {
      connection = { ...base, credentials_set: true }
      return { revoked: true }
    }
    return undefined
  })
})
afterEach(() => vi.unstubAllGlobals())

function renderSection(url = '/settings') {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[url]}>
        <GmailSection />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('GmailSection', () => {
  it('US1 AS1 explains read-only and links the guide', async () => {
    renderSection()

    const section = await screen.findByRole('region', {
      name: 'Gmail job alerts',
    })
    expect(within(section).getByText(/only read/i)).toBeInTheDocument()
    expect(within(section).getByText(/never sends, deletes or changes/i)).toBeInTheDocument()
    expect(await within(section).findByText('Not connected')).toBeInTheDocument()
    const guide = within(section).getByRole('link', { name: /setup guide/i })
    expect(guide).toHaveAttribute('href', expect.stringContaining('docs/gmail-setup.md'))
  })

  it('US1 AS5 asks for the two values and shows the address to register', async () => {
    renderSection()

    expect(await screen.findByLabelText('Client ID')).toBeInTheDocument()
    expect(screen.getByLabelText('Client secret')).toHaveAttribute('type', 'password')
    expect(screen.getByText(REDIRECT)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Connect Gmail' })).not.toBeInTheDocument()
  })

  it('US1 AS5 saves the two values, then offers Connect', async () => {
    renderSection()
    await userEvent.type(await screen.findByLabelText('Client ID'), 'client-id-1234567890')
    await userEvent.type(screen.getByLabelText('Client secret'), 'client-secret-1234567890')

    await userEvent.click(screen.getByRole('button', { name: 'Save' }))

    const put = await waitFor(() => {
      const found = calls.find((c) => c.method === 'PUT')
      expect(found).toBeDefined()
      return found
    })
    expect(put?.body).toEqual({
      client_id: 'client-id-1234567890',
      client_secret: 'client-secret-1234567890',
    })
    expect(await screen.findByRole('button', { name: 'Connect Gmail' })).toBeInTheDocument()
    expect(screen.queryByLabelText('Client secret')).not.toBeInTheDocument() // never shown again
  })

  it('US1 AS5 a value with a space is refused before it is sent', async () => {
    renderSection()
    await userEvent.type(await screen.findByLabelText('Client ID'), 'client id with spaces')
    await userEvent.type(screen.getByLabelText('Client secret'), 'client-secret-1234567890')

    await userEvent.click(screen.getByRole('button', { name: 'Save' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/no spaces/i)
    expect(calls.some((c) => c.method === 'PUT')).toBe(false)
  })

  it('US1 AS2 Connect goes to Google', async () => {
    connection = { ...base, credentials_set: true }
    renderSection()

    await userEvent.click(await screen.findByRole('button', { name: 'Connect Gmail' }))

    await waitFor(() =>
      expect(assign).toHaveBeenCalledWith('https://accounts.example.invalid/auth?state=s'),
    )
  })

  it('US1 AS5 Connect without saved values says what is missing', async () => {
    connection = { ...base, credentials_set: true }
    stubApi((call) => {
      if (call.path === '/mail/connection') return connection
      if (call.path === '/mail/connect')
        return problem(409, 'Save your Google client id and secret first.', {
          reason: 'no_credentials',
          detail: 'Save your Google client id and secret first.',
        })
      return undefined
    })
    renderSection()

    await userEvent.click(await screen.findByRole('button', { name: 'Connect Gmail' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/client id and secret/i)
    expect(assign).not.toHaveBeenCalled()
  })

  it('US5 AS5 says each check reads the last 24 hours and when the last one ran', async () => {
    connection = {
      ...base,
      state: 'connected',
      address: 'jobseeker@example.invalid',
      credentials_set: true,
      last_check_started_at: '2026-11-18T12:00:00Z',
    }
    renderSection()

    expect(
      await screen.findByText('Each check reads job-alert emails from the last 24 hours.'),
    ).toBeInTheDocument()
    expect(screen.getByText(/^Last check: 18 Nov 2026, \d\d:\d\d$/)).toBeInTheDocument()
  })

  it('US5 AS5 the window comes from the server and shows while access has ended', async () => {
    connection = {
      ...base,
      state: 'needs_reconnect',
      address: 'jobseeker@example.invalid',
      credentials_set: true,
      window_hours: 48,
      last_error: 'Gmail access has ended.',
    }
    renderSection()

    expect(
      await screen.findByText('Each check reads job-alert emails from the last 48 hours.'),
    ).toBeInTheDocument()
  })

  it('US5 AS5 a connection that was never checked says so', async () => {
    connection = {
      ...base,
      state: 'connected',
      address: 'jobseeker@example.invalid',
      credentials_set: true,
    }
    renderSection()

    expect(await screen.findByText('Not checked yet.')).toBeInTheDocument()
  })

  it('US5 AS5 the 24 hours note is not shown when Gmail is not connected', async () => {
    connection = { ...base, credentials_set: true }
    renderSection()

    await screen.findByRole('button', { name: 'Connect Gmail' })
    expect(screen.queryByText(/from the last 24 hours/)).not.toBeInTheDocument()
  })

  it('US1 AS2 connected as', async () => {
    connection = {
      ...base,
      state: 'connected',
      address: 'jobseeker@example.invalid',
      credentials_set: true,
    }
    renderSection()

    expect(await screen.findByText('Connected as jobseeker@example.invalid')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Disconnect' })).toBeInTheDocument()
    expect(screen.queryByLabelText('Client secret')).not.toBeInTheDocument()
  })

  it('US1 AS3 disconnect asks then shows not connected', async () => {
    connection = {
      ...base,
      state: 'connected',
      address: 'jobseeker@example.invalid',
      credentials_set: true,
    }
    renderSection()

    await userEvent.click(await screen.findByRole('button', { name: 'Disconnect' }))
    const dialog = await screen.findByRole('alertdialog')
    expect(dialog).toHaveTextContent(/jobs.*stay/i)
    expect(calls.some((c) => c.method === 'DELETE')).toBe(false) // asked first
    await userEvent.click(within(dialog).getByRole('button', { name: 'Disconnect Gmail' }))

    await waitFor(() => expect(calls.some((c) => c.method === 'DELETE')).toBe(true))
    expect(await screen.findByText('Not connected')).toBeInTheDocument()
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()
  })

  it('US1 AS3 Cancel leaves it connected', async () => {
    connection = {
      ...base,
      state: 'connected',
      address: 'a@example.invalid',
      credentials_set: true,
    }
    renderSection()

    await userEvent.click(await screen.findByRole('button', { name: 'Disconnect' }))
    await userEvent.click(
      within(await screen.findByRole('alertdialog')).getByRole('button', {
        name: 'Cancel',
      }),
    )

    expect(calls.some((c) => c.method === 'DELETE')).toBe(false)
    expect(screen.getByText('Connected as a@example.invalid')).toBeInTheDocument()
  })

  it('US1 AS4 reconnect notice', async () => {
    connection = {
      ...base,
      state: 'needs_reconnect',
      address: 'jobseeker@example.invalid',
      credentials_set: true,
      last_error: 'Gmail access has ended. Connect again.',
    }
    renderSection()

    expect(await screen.findByRole('alert')).toHaveTextContent('Gmail access has ended')
    await userEvent.click(screen.getByRole('button', { name: 'Reconnect Gmail' }))
    await waitFor(() => expect(assign).toHaveBeenCalled())
  })

  it('credentials set in the environment are not asked for', async () => {
    connection = {
      ...base,
      credentials_set: true,
      credentials_from_environment: true,
    }
    renderSection()

    expect(await screen.findByText(/set in the environment/i)).toBeInTheDocument()
    expect(screen.queryByLabelText('Client ID')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Connect Gmail' })).toBeInTheDocument()
  })

  it('reads ?gmail=connected after Google sends the person back', async () => {
    connection = {
      ...base,
      state: 'connected',
      address: 'a@example.invalid',
      credentials_set: true,
    }
    renderSection('/settings?gmail=connected')

    expect(await screen.findByRole('status', { name: /gmail result/i })).toHaveTextContent(
      'Gmail is connected.',
    )
  })

  it.each([
    ['denied', /did not allow/i],
    ['wrong_scope', /more than read-only/i],
    ['state', /took too long|try again/i],
    ['exchange_failed', /could not finish/i],
  ])('reads ?gmail=error&reason=%s', async (reason, text) => {
    renderSection(`/settings?gmail=error&reason=${reason}`)

    expect(await screen.findByRole('alert', { name: /gmail result/i })).toHaveTextContent(text)
  })

  it('an unknown reason is shown plainly, not as raw text from the address', async () => {
    renderSection('/settings?gmail=error&reason=%3Cscript%3E')

    const alert = await screen.findByRole('alert', { name: /gmail result/i })
    expect(alert).toHaveTextContent(/did not work/i)
    expect(alert).not.toHaveTextContent('<script>')
  })

  it('Change client ID and secret saves, then closes the form', async () => {
    connection = { ...base, credentials_set: true }
    renderSection()

    await userEvent.click(
      await screen.findByRole('button', { name: 'Change client ID and secret' }),
    )
    await userEvent.type(screen.getByLabelText('Client ID'), 'another-client-id-1234')
    await userEvent.type(screen.getByLabelText('Client secret'), 'another-secret-12345')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => expect(calls.some((c) => c.method === 'PUT')).toBe(true))
    await waitFor(() => expect(screen.queryByLabelText('Client secret')).not.toBeInTheDocument())
    expect(screen.getByRole('button', { name: 'Change client ID and secret' })).toBeInTheDocument()
    expect(document.body.textContent).not.toContain('another-secret-12345')
  })

  it('Change client ID and secret can be cancelled without saving', async () => {
    connection = { ...base, credentials_set: true }
    renderSection()

    await userEvent.click(
      await screen.findByRole('button', { name: 'Change client ID and secret' }),
    )
    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }))

    expect(screen.queryByLabelText('Client secret')).not.toBeInTheDocument()
    expect(calls.some((c) => c.method === 'PUT')).toBe(false)
  })

  it('the client secret field is a new-password field so managers do not fill their own login', async () => {
    renderSection()

    expect(await screen.findByLabelText('Client secret')).toHaveAttribute(
      'autocomplete',
      'new-password',
    )
  })

  it('a stale ?gmail=connected is not shown once Gmail is not connected', async () => {
    renderSection('/settings?gmail=connected') // not connected, e.g. after a later Disconnect

    await screen.findByText('Not connected')

    expect(screen.queryByText('Gmail is connected.')).not.toBeInTheDocument()
  })

  it('refuses to navigate to an address that is not https', async () => {
    connection = { ...base, credentials_set: true }
    stubApi((call) => {
      if (call.path === '/mail/connection') return connection
      if (call.path === '/mail/connect') return { authorize_url: 'javascript:alert(1)' }
      return undefined
    })
    renderSection()

    await userEvent.click(await screen.findByRole('button', { name: 'Connect Gmail' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/could not be started/i)
    expect(assign).not.toHaveBeenCalled()
  })

  it('the reconnect notice is an alert', async () => {
    connection = {
      ...base,
      state: 'needs_reconnect',
      address: 'a@example.invalid',
      credentials_set: true,
      last_error: 'Gmail access has ended. Connect again.',
    }
    renderSection()

    expect(await screen.findByRole('alert')).toHaveTextContent('Gmail access has ended')
  })

  it('US1 AS3 says so when Google could not be reached to take the access back', async () => {
    connection = {
      ...base,
      state: 'connected',
      address: 'a@example.invalid',
      credentials_set: true,
    }
    stubApi((call) => {
      if (call.method === 'GET' && call.path === '/mail/connection') return connection
      if (call.method === 'DELETE') {
        connection = { ...base, credentials_set: true }
        return { revoked: false }
      }
      return undefined
    })
    renderSection()

    await userEvent.click(await screen.findByRole('button', { name: 'Disconnect' }))
    await userEvent.click(
      within(await screen.findByRole('alertdialog')).getByRole('button', {
        name: 'Disconnect Gmail',
      }),
    )

    const notice = await screen.findByRole('alert', { name: /disconnect result/i })
    expect(notice).toHaveTextContent(/could not be reached/i)
    expect(notice).toHaveTextContent(/myaccount\.google\.com\/permissions/)
    expect(await screen.findByText('Not connected')).toBeInTheDocument()
  })

  it('US1 AS3 a confirmed revoke shows no warning', async () => {
    connection = {
      ...base,
      state: 'connected',
      address: 'a@example.invalid',
      credentials_set: true,
    }
    renderSection()

    await userEvent.click(await screen.findByRole('button', { name: 'Disconnect' }))
    await userEvent.click(
      within(await screen.findByRole('alertdialog')).getByRole('button', {
        name: 'Disconnect Gmail',
      }),
    )

    expect(await screen.findByText('Not connected')).toBeInTheDocument()
    expect(screen.queryByRole('alert', { name: /disconnect result/i })).not.toBeInTheDocument()
  })

  it('shows a checklist with direct links to the Google pages', async () => {
    renderSection()

    const list = await screen.findByRole('list', { name: /setup steps/i })
    const hrefs = within(list)
      .getAllByRole('link')
      .map((a) => a.getAttribute('href'))
    expect(hrefs).toEqual(
      expect.arrayContaining([
        expect.stringContaining('console.cloud.google.com/projectcreate'),
        expect.stringContaining('gmail.googleapis.com'),
        expect.stringContaining('console.cloud.google.com/apis/credentials'),
      ]),
    )
    for (const a of within(list).getAllByRole('link'))
      expect(a).toHaveAttribute('rel', 'noreferrer')
  })

  it('the redirect address can be copied', async () => {
    const user = userEvent.setup()
    renderSection()

    await user.click(await screen.findByRole('button', { name: 'Copy redirect address' }))

    expect(await screen.findByText('Copied')).toBeInTheDocument()
    expect(await navigator.clipboard.readText()).toBe(REDIRECT)
  })

  it('loads the two values from the downloaded client_secret.json', async () => {
    const user = userEvent.setup()
    renderSection()
    const file = new File(
      [
        JSON.stringify({
          web: { client_id: 'file-client-id-1234.apps', client_secret: 'file-secret-12345' },
        }),
      ],
      'client_secret.json',
      { type: 'application/json' },
    )

    await user.upload(await screen.findByLabelText(/load client_secret\.json/i), file)

    expect(await screen.findByDisplayValue('file-client-id-1234.apps')).toBeInTheDocument()
    expect(screen.getByLabelText('Client secret')).toHaveValue('file-secret-12345')
    expect(calls.some((c) => c.method === 'PUT')).toBe(false) // nothing is sent until Save
  })

  it('a Desktop client file is refused with what to do instead', async () => {
    const user = userEvent.setup()
    renderSection()
    const file = new File(
      [
        JSON.stringify({
          installed: { client_id: 'desktop-client-id-1234', client_secret: 'x'.repeat(12) },
        }),
      ],
      'client_secret.json',
      { type: 'application/json' },
    )

    await user.upload(await screen.findByLabelText(/load client_secret\.json/i), file)

    expect(await screen.findByRole('alert')).toHaveTextContent(/web application/i)
    expect(screen.getByLabelText('Client ID')).toHaveValue('')
  })

  it('a file that is not a Google client file is refused', async () => {
    const user = userEvent.setup()
    renderSection()
    const file = new File(['not json at all'], 'client_secret.json', { type: 'application/json' })

    await user.upload(await screen.findByLabelText(/load client_secret\.json/i), file)

    expect(await screen.findByRole('alert')).toHaveTextContent(/not a google client file/i)
  })
})

describe('GmailSection: the set-up as steps (US6)', () => {
  function steps() {
    // the steps themselves, not the items of a list inside a step
    return Array.from(screen.getByRole('list', { name: 'Gmail set-up steps' }).children) as HTMLElement[]
  }

  function step(n: number): HTMLElement {
    const found = steps()[n]
    if (!found) throw new Error(`no step ${n + 1}`)
    return found
  }

  it('US6 AS5 a fresh install shows four steps, the first open and the rest waiting', async () => {
    renderSection()

    await screen.findByRole('list', { name: 'Gmail set-up steps' })
    const [client, connect, senders, check] = [step(0), step(1), step(2), step(3)]
    expect(client).toHaveAttribute('aria-current', 'step')
    expect(within(client).getByRole('heading', { name: 'Google client' })).toBeInTheDocument()
    expect(within(client).getByLabelText('Client ID')).toBeInTheDocument() // open
    expect(within(connect).getByText('Waits for Google client')).toBeInTheDocument()
    expect(within(senders).getByText('Waits for Connect')).toBeInTheDocument()
    expect(within(check).getByText('Waits for Connect')).toBeInTheDocument()
  })

  it('US6 AS5 saving the client marks it done and opens Connect', async () => {
    const user = userEvent.setup()
    renderSection()

    await user.type(await screen.findByLabelText('Client ID'), 'client-id-0123456789')
    await user.type(screen.getByLabelText('Client secret'), 'client-secret-0123456789')
    await user.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => expect(step(1)).toHaveAttribute('aria-current', 'step'))
    expect(within(step(0)).getByText('Done')).toBeInTheDocument()
    expect(within(step(0)).getByText('Client ID and secret saved.')).toBeInTheDocument()
    expect(within(step(1)).getByRole('button', { name: 'Connect Gmail' })).toBeInTheDocument()
  })

  it('US6 AS6 connected: the senders step shows a summary and opens to the list', async () => {
    connection = { ...base, state: 'connected', address: 'jobseeker@example.invalid', credentials_set: true }
    const user = userEvent.setup()
    calls = stubApi((call) => {
      if (call.path === '/mail/connection') return connection
      if (call.path === '/mail/senders')
        return {
          items: [
            { id: 's1', address: 'jobalerts-noreply@linkedin.com', site: 'linkedin', built_in: true, enabled: true },
            { id: 's2', address: 'naukrialerts@naukri.com', site: 'naukri', built_in: true, enabled: false },
          ],
        }
      return undefined
    })
    renderSection()

    await screen.findByText(/1 of 2 senders on/)
    const senders = step(2)
    await user.click(within(senders).getByRole('button', { name: 'Show senders' }))

    expect(await within(senders).findByRole('group', { name: 'LinkedIn' })).toBeInTheDocument()
    expect(within(senders).getByRole('button', { name: 'Hide senders' })).toHaveAttribute(
      'aria-expanded',
      'true',
    )
  })

  it('US6 AS5 connected and never checked: the first check is next and can be started', async () => {
    connection = { ...base, state: 'connected', address: 'jobseeker@example.invalid', credentials_set: true }
    const user = userEvent.setup()
    calls = stubApi((call) => {
      if (call.path === '/mail/connection') return connection
      if (call.method === 'POST' && call.path === '/mail/checks')
        return new Response(JSON.stringify({ search_run_id: 'r1' }), { status: 202 })
      return undefined
    })
    renderSection()

    await screen.findByRole('list', { name: 'Gmail set-up steps' })
    const check = step(3)
    expect(check).toHaveAttribute('aria-current', 'step')
    await user.click(within(check).getByRole('button', { name: 'Check job-alert mail' }))

    await waitFor(() =>
      expect(calls.some((c) => c.method === 'POST' && c.path === '/mail/checks')).toBe(true),
    )
    expect(await within(check).findByRole('link', { name: 'Explore' })).toHaveAttribute('href', '/')
  })

  it('US6 AS5 everything done: no step is current, each keeps its summary', async () => {
    connection = {
      ...base,
      state: 'connected',
      address: 'jobseeker@example.invalid',
      credentials_set: true,
      last_check_started_at: '2026-11-22T12:00:00Z',
    }
    renderSection()

    await screen.findByRole('list', { name: 'Gmail set-up steps' })
    expect(steps().filter((s) => s.getAttribute('aria-current') === 'step')).toEqual([])
    expect(screen.getByText('Connected as jobseeker@example.invalid')).toBeInTheDocument()
    expect(screen.getByText(/Last check:/)).toBeInTheDocument()
    expect(screen.getAllByText('Done')).toHaveLength(4)
  })
})

describe('GmailSection: review fixes', () => {
  function steps() {
    return Array.from(
      screen.getByRole('list', { name: 'Gmail set-up steps' }).children,
    ) as HTMLElement[]
  }
  const linkedin = {
    items: [
      { id: 's1', address: 'a@linkedin.com', site: 'linkedin', built_in: true, enabled: true },
    ],
  }

  it('after Disconnect an opened step closes and the new current step opens', async () => {
    connection = {
      ...base,
      state: 'connected',
      address: 'jobseeker@example.invalid',
      credentials_set: true,
    }
    const user = userEvent.setup()
    calls = stubApi((call) => {
      if (call.method === 'DELETE' && call.path === '/mail/connection') {
        connection = { ...base, credentials_set: true }
        return { revoked: true }
      }
      if (call.path === '/mail/connection') return connection
      if (call.path === '/mail/senders') return linkedin
      return undefined
    })
    renderSection()

    await user.click(await screen.findByRole('button', { name: 'Show senders' }))
    await screen.findByRole('group', { name: 'LinkedIn' })
    await user.click(screen.getByRole('button', { name: 'Disconnect' }))
    await user.click(await screen.findByRole('button', { name: 'Disconnect Gmail' }))

    await waitFor(() =>
      expect(screen.queryByRole('group', { name: 'LinkedIn' })).not.toBeInTheDocument(),
    )
    const connect = steps()[1] as HTMLElement
    expect(connect).toHaveAttribute('aria-current', 'step')
    expect(within(connect).getByRole('button', { name: 'Connect Gmail' })).toBeInTheDocument()
  })

  it('access ended: the summary does not say connected, and the client can be changed', async () => {
    connection = {
      ...base,
      state: 'needs_reconnect',
      address: 'jobseeker@example.invalid',
      credentials_set: true,
      last_error: 'Gmail access has ended. Connect again.',
    }
    renderSection()

    expect(
      await screen.findByText('Was connected as jobseeker@example.invalid.'),
    ).toBeInTheDocument()
    expect(screen.queryByText('Connected as jobseeker@example.invalid')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Change client ID and secret' })).toBeInTheDocument()
  })

  it('once checked, the check step offers the check itself, not a second click', async () => {
    connection = {
      ...base,
      state: 'connected',
      address: 'jobseeker@example.invalid',
      credentials_set: true,
      last_check_started_at: '2026-11-22T12:00:00Z',
    }
    renderSection()

    await screen.findByRole('list', { name: 'Gmail set-up steps' })
    const check = steps()[3] as HTMLElement
    expect(within(check).getByRole('button', { name: 'Check job-alert mail' })).toBeInTheDocument()
  })

  it('Disconnect is offered once, in the Connect step', async () => {
    connection = {
      ...base,
      state: 'connected',
      address: 'jobseeker@example.invalid',
      credentials_set: true,
    }
    renderSection()

    await screen.findByText('Connected as jobseeker@example.invalid')
    expect(screen.getAllByRole('button', { name: 'Disconnect' })).toHaveLength(1)
  })

  it('the senders step has one heading, the step title', async () => {
    connection = {
      ...base,
      state: 'connected',
      address: 'jobseeker@example.invalid',
      credentials_set: true,
    }
    const user = userEvent.setup()
    calls = stubApi((call) => {
      if (call.path === '/mail/connection') return connection
      if (call.path === '/mail/senders') return linkedin
      return undefined
    })
    renderSection()

    await user.click(await screen.findByRole('button', { name: 'Show senders' }))
    expect(
      screen.queryByRole('heading', { name: 'Senders HireTitan reads' }),
    ).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Senders' })).toBeInTheDocument()
  })
})
