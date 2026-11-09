import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { json, problem, stubApi, type Call } from '@/test/api'
import { CompanyPanel } from './CompanyPanel'

const COMPANY = 'c1'
const JANE = {
  id: 'k1',
  company_id: COMPANY,
  name: 'Jane Example',
  role: 'Recruiter',
  linkedin_url: 'https://www.linkedin.com/in/jane-example',
  email: 'jane@example.com',
  phone: '+91 98765 43210',
  confidence: 'high',
  note: 'Replies fast.',
  source: 'typed',
  updated_at: '2026-11-09T09:00:00Z',
}
const PANEL = {
  items: [JANE],
  note: {
    body: 'Spoke to HR on Monday.',
    source: 'typed',
    updated_at: '2026-11-09T09:00:00Z',
  },
}

function renderIt(handler: (call: Call) => unknown) {
  const calls = stubApi(handler)
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <CompanyPanel companyId={COMPANY} companyName="Example Co" />
    </QueryClientProvider>,
  )
  return calls
}

const list = (call: Call) =>
  call.path === `/companies/${COMPANY}/contacts` && call.method === 'GET' ? PANEL : undefined

afterEach(() => vi.unstubAllGlobals())

describe('CompanyPanel', () => {
  it('US2 AS1 shows contacts and note', async () => {
    renderIt(list)

    const contacts = await screen.findByRole('list', {
      name: 'Contacts at Example Co',
    })
    expect(contacts).toHaveTextContent('Jane Example')
    expect(contacts).toHaveTextContent('Recruiter')
    expect(contacts).toHaveTextContent('high confidence')
    expect(contacts).toHaveTextContent('Replies fast.')
    expect(screen.getByLabelText('Note about Example Co')).toHaveValue('Spoke to HR on Monday.')
  })

  it('shows an empty state when there are no contacts', async () => {
    renderIt(() => ({ items: [], note: null }))

    expect(await screen.findByText('No contacts yet.')).toBeInTheDocument()
    expect(screen.getByLabelText('Note about Example Co')).toHaveValue('')
  })

  it('US2 AS2 adds a contact with only a name', async () => {
    const user = userEvent.setup()
    const calls = renderIt((call) => {
      if (call.method === 'POST' && call.path === `/companies/${COMPANY}/contacts`)
        return { ...JANE, name: 'Only Name', role: null, linkedin_url: null }
      return list(call)
    })
    await screen.findByRole('list', { name: 'Contacts at Example Co' })

    await user.click(screen.getByRole('button', { name: 'Add a contact' }))
    await user.type(screen.getByLabelText('Name'), 'Only Name')
    await user.click(screen.getByRole('button', { name: 'Save contact' }))

    await waitFor(() => expect(calls.some((c) => c.method === 'POST')).toBe(true))
    const post = calls.find((c) => c.method === 'POST')
    expect(post?.body).toMatchObject({ name: 'Only Name' })
  })

  it('US2 AS3 edit and delete with confirmation', async () => {
    const user = userEvent.setup()
    const calls = renderIt((call) => {
      if (call.method === 'PATCH') return { ...JANE, role: 'Talent Lead' }
      if (call.method === 'DELETE') return new Response(null, { status: 204 })
      return list(call)
    })
    await screen.findByRole('list', { name: 'Contacts at Example Co' })

    await user.click(screen.getByRole('button', { name: 'Edit Jane Example' }))
    const role = screen.getByLabelText('Role')
    await user.clear(role)
    await user.type(role, 'Talent Lead')
    await user.click(screen.getByRole('button', { name: 'Save contact' }))
    await waitFor(() => expect(calls.some((c) => c.method === 'PATCH')).toBe(true))
    expect(calls.find((c) => c.method === 'PATCH')?.path).toBe(`/companies/${COMPANY}/contacts/k1`)

    await user.click(screen.getByRole('button', { name: 'Delete Jane Example' }))
    expect(screen.getByText(/Delete Jane Example\?/)).toBeInTheDocument()
    expect(calls.some((c) => c.method === 'DELETE')).toBe(false) // asks first
    await user.click(screen.getByRole('button', { name: 'Yes, delete' }))
    await waitFor(() => expect(calls.some((c) => c.method === 'DELETE')).toBe(true))
  })

  it('keeps the contact when the person says no to the delete', async () => {
    const user = userEvent.setup()
    const calls = renderIt(list)
    await screen.findByRole('list', { name: 'Contacts at Example Co' })

    await user.click(screen.getByRole('button', { name: 'Delete Jane Example' }))
    await user.click(screen.getByRole('button', { name: 'Keep it' }))

    expect(calls.some((c) => c.method === 'DELETE')).toBe(false)
    expect(screen.getByText('Jane Example')).toBeInTheDocument()
  })

  it('US2 AS4 link opens in a new tab with rel noopener noreferrer and is never fetched', async () => {
    const calls = renderIt(list)

    const link = await screen.findByRole('link', {
      name: /LinkedIn.*Jane Example/,
    })

    expect(link).toHaveAttribute('href', JANE.linkedin_url)
    expect(link).toHaveAttribute('target', '_blank')
    expect(link).toHaveAttribute('rel', 'noopener noreferrer')
    expect(calls.every((c) => c.path.startsWith('/companies/'))).toBe(true) // only our own API
  })

  it('US2 AS6 shows the field error for a bad link', async () => {
    const user = userEvent.setup()
    renderIt((call) => {
      if (call.method === 'POST')
        return problem(422, 'Unprocessable', {
          detail: 'The link must be a web address.',
          errors: [
            {
              field: 'linkedin_url',
              message: 'The link must be a web address.',
            },
          ],
        })
      return list(call)
    })
    await screen.findByRole('list', { name: 'Contacts at Example Co' })

    await user.click(screen.getByRole('button', { name: 'Add a contact' }))
    await user.type(screen.getByLabelText('Name'), 'Bad Link')
    await user.type(screen.getByLabelText('LinkedIn link'), 'not a link')
    await user.click(screen.getByRole('button', { name: 'Save contact' }))

    expect(await screen.findByText('The link must be a web address.')).toBeInTheDocument()
    expect(screen.getByLabelText('LinkedIn link')).toHaveAttribute('aria-invalid', 'true')
  })

  it('shows a name that already exists as a message', async () => {
    const user = userEvent.setup()
    renderIt((call) => {
      if (call.method === 'POST')
        return problem(409, 'Conflict', {
          detail: 'Jane Example is already a contact here.',
        })
      return list(call)
    })
    await screen.findByRole('list', { name: 'Contacts at Example Co' })

    await user.click(screen.getByRole('button', { name: 'Add a contact' }))
    await user.type(screen.getByLabelText('Name'), 'Jane Example')
    await user.click(screen.getByRole('button', { name: 'Save contact' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('already a contact')
  })

  it('email and phone render as plain text, not links', async () => {
    renderIt(list)

    const contacts = await screen.findByRole('list', {
      name: 'Contacts at Example Co',
    })

    expect(contacts).toHaveTextContent('jane@example.com')
    expect(contacts).toHaveTextContent('+91 98765 43210')
    const links = within(contacts).getAllByRole('link')
    expect(links).toHaveLength(1) // only the LinkedIn link
    expect(contacts.querySelector('a[href^="mailto:"]')).toBeNull()
    expect(contacts.querySelector('a[href^="tel:"]')).toBeNull()
  })

  it('renders hostile text as text', async () => {
    renderIt(() => ({
      items: [{ ...JANE, name: '<b>Bold</b>', note: '<img src=x onerror=alert(1)>' }],
      note: null,
    }))

    const contacts = await screen.findByRole('list', {
      name: 'Contacts at Example Co',
    })

    expect(contacts).toHaveTextContent('<b>Bold</b>')
    expect(contacts.querySelector('b')).toBeNull()
    expect(contacts.querySelector('img')).toBeNull()
  })

  it('FR010 saves and clears the note', async () => {
    const user = userEvent.setup()
    const calls = renderIt((call) => {
      if (call.method === 'PUT')
        return json({
          body: (call.body as { body: string }).body || null,
          source: 'typed',
          updated_at: null,
        })
      return list(call)
    })
    const note = await screen.findByLabelText('Note about Example Co')

    await user.clear(note)
    await user.type(note, 'New thoughts')
    await user.click(screen.getByRole('button', { name: 'Save note' }))
    await waitFor(() => expect(calls.some((c) => c.method === 'PUT')).toBe(true))
    expect(calls.find((c) => c.method === 'PUT')?.body).toEqual({
      body: 'New thoughts',
    })

    await user.clear(note)
    await user.click(screen.getByRole('button', { name: 'Save note' }))
    await waitFor(() => expect(calls.filter((c) => c.method === 'PUT')).toHaveLength(2))
    expect(calls.filter((c) => c.method === 'PUT')[1]?.body).toEqual({
      body: '',
    })
  })
})
