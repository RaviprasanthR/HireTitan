import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { LinkedinImport } from './LinkedinImport'

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': status < 400 ? 'application/json' : 'application/problem+json' },
  })

const CSV =
  'First Name,Last Name,URL,Email Address,Company,Position,Connected On\nAsha,Rao,,,Acme,SDE,'

let calls: { method: string; url: string; body: unknown }[]
let answer: () => Response

beforeEach(() => {
  calls = []
  answer = () =>
    json({
      added: 3,
      companies_with_new_contacts: 2,
      already_there: 0,
      skipped_companies: 7,
      invalid_rows: 0,
      truncated: false,
    })
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      calls.push({
        method: init?.method ?? 'GET',
        url,
        body: init?.body ? JSON.parse(String(init.body)) : undefined,
      })
      return answer()
    }),
  )
})
afterEach(() => vi.unstubAllGlobals())

function renderImport() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <LinkedinImport />
    </QueryClientProvider>,
  )
}

const csvFile = () => new File([CSV], 'Connections.csv', { type: 'text/csv' })

describe('LinkedinImport', () => {
  it('sends the file text to this install and reports what was added', async () => {
    renderImport()
    await userEvent.upload(screen.getByLabelText('LinkedIn Connections.csv'), csvFile())

    expect(await screen.findByRole('status')).toHaveTextContent(
      'Added 3 people at 2 companies; 7 employers are not on your list.',
    )
    expect(calls).toEqual([
      { method: 'POST', url: '/api/v1/companies/contacts/linkedin-import', body: { csv: CSV } },
    ])
  })

  it('says how many were already there when the same file is uploaded again', async () => {
    answer = () =>
      json({
        added: 0,
        companies_with_new_contacts: 0,
        already_there: 3,
        skipped_companies: 7,
        invalid_rows: 0,
        truncated: false,
      })
    renderImport()
    await userEvent.upload(screen.getByLabelText('LinkedIn Connections.csv'), csvFile())

    expect(await screen.findByRole('status')).toHaveTextContent(
      'Added 0 people at 0 companies, 3 already there; 7 employers are not on your list.',
    )
  })

  it('says how many rows could not be kept and when the file was cut short', async () => {
    answer = () =>
      json({
        added: 1,
        companies_with_new_contacts: 1,
        already_there: 0,
        skipped_companies: 0,
        invalid_rows: 2,
        truncated: true,
      })
    renderImport()
    await userEvent.upload(screen.getByLabelText('LinkedIn Connections.csv'), csvFile())

    const said = await screen.findByText(/2 rows had details that could not be kept/)
    expect(said).toHaveTextContent('only the first 20,000 people were read')
  })

  it('shows the server problem when the file is refused', async () => {
    answer = () =>
      json({ title: 'Invalid', detail: 'This is not a LinkedIn Connections.csv.' }, 422)
    renderImport()
    await userEvent.upload(screen.getByLabelText('LinkedIn Connections.csv'), csvFile())

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'This is not a LinkedIn Connections.csv.',
    )
    expect(screen.getByRole('status')).toBeEmptyDOMElement()
  })
})
