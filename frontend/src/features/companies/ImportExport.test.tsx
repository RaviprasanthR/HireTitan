import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { stubApi, type Call } from '@/test/api'
import { ImportExport } from './ImportExport'

const PREVIEW = {
  add: [
    {
      row: 3,
      name: 'Brand New',
      city: 'Chennai',
      website: null,
      careers_url: 'https://new.example.com/jobs',
      ats_vendor: null,
      board_id: null,
      hidden: null,
    },
  ],
  update: [
    { row: 2, id: 'a', name: 'Acme', changes: { city: { from: 'Pune', to: 'Bengaluru' } } },
  ],
  invalid: [{ row: 4, reason: 'The company needs a name.' }],
  token: 'tok123',
}

function renderIt(handler: (call: Call) => unknown) {
  const calls = stubApi(handler)
  render(
    <QueryClientProvider client={new QueryClient()}>
      <ImportExport />
    </QueryClientProvider>,
  )
  return calls
}

afterEach(() => vi.unstubAllGlobals())

describe('ImportExport', () => {
  it('links_to_the_export', () => {
    renderIt(() => undefined)

    expect(screen.getByRole('link', { name: 'Export CSV' })).toHaveAttribute(
      'href',
      '/api/v1/companies/export',
    )
  })

  it('US3_AS6_preview_then_confirm', async () => {
    const user = userEvent.setup()
    const calls = renderIt((call) => {
      if (call.path === '/companies/import') return PREVIEW
      if (call.path === '/companies/import/tok123/confirm') return { added: 1, updated: 1 }
      return undefined
    })

    await user.upload(
      screen.getByLabelText('Import CSV'),
      new File(['name\nBrand New'], 'companies.csv', { type: 'text/csv' }),
    )

    const preview = await screen.findByRole('region', { name: 'Import preview' })
    expect(preview).toHaveTextContent('1 to add')
    expect(preview).toHaveTextContent('1 to update')
    expect(preview).toHaveTextContent('Brand New')
    expect(preview).toHaveTextContent('Pune → Bengaluru')
    expect(within(preview).getByText(/Row 4/)).toHaveTextContent('The company needs a name.')
    expect(calls.some((c) => c.path.endsWith('/confirm'))).toBe(false) // nothing yet

    await user.click(screen.getByRole('button', { name: 'Confirm import' }))

    expect(await screen.findByText('Added 1 and updated 1.')).toBeInTheDocument()
    await waitFor(() =>
      expect(screen.queryByRole('region', { name: 'Import preview' })).toBeNull(),
    )
  })

  it('cancel_leaves_everything_as_it_was', async () => {
    const user = userEvent.setup()
    const calls = renderIt((call) => (call.path === '/companies/import' ? PREVIEW : undefined))

    await user.upload(screen.getByLabelText('Import CSV'), new File(['x'], 'c.csv'))
    await user.click(await screen.findByRole('button', { name: 'Cancel' }))

    expect(screen.queryByRole('region', { name: 'Import preview' })).toBeNull()
    expect(calls.some((c) => c.path.endsWith('/confirm'))).toBe(false)
  })

  it('shows_why_a_file_was_refused', async () => {
    const user = userEvent.setup()
    renderIt(
      () =>
        new Response(
          JSON.stringify({
            title: 'Unprocessable',
            status: 422,
            detail: 'The file has more than 2,000 rows.',
          }),
          { status: 422, headers: { 'Content-Type': 'application/problem+json' } },
        ),
    )

    await user.upload(screen.getByLabelText('Import CSV'), new File(['x'], 'c.csv'))

    expect(await screen.findByRole('alert')).toHaveTextContent('more than 2,000 rows')
  })
})
