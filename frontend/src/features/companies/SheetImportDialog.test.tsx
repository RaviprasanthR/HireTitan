import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { problem, stubApi, type Call } from '@/test/api'
import { SheetImportDialog } from './SheetImportDialog'

const PREVIEW = {
  token: 'sheet123',
  columns: { used: ['name', 'location', 'contacts'], ignored: ['Frontend openings', 'Budget'] },
  companies: { matched: 3, to_add: 2 },
  contacts: { to_add: 12, to_update: 1 },
  notes: { to_set: 2, to_change: 1, kept_yours: 1 },
  rows: [],
  skipped: [
    { line: 9, reason: 'The row has no company name.' },
    { line: 12, reason: 'The row matches two companies: Example Alpha, Example Beta.' },
  ],
  shortened: [{ line: 15, reason: 'More than 20 people in the cell; kept the first 20.' }],
}
const NOTHING = {
  ...PREVIEW,
  companies: { matched: 5, to_add: 0 },
  contacts: { to_add: 0, to_update: 0 },
  notes: { to_set: 0, to_change: 0, kept_yours: 0 },
  skipped: [],
  shortened: [],
}
const RESULT = {
  matched: 3,
  companies_added: 2,
  contacts_added: 12,
  contacts_updated: 1,
  notes_set: 2,
  notes_changed: 1,
  notes_kept: 1,
  skipped: PREVIEW.skipped,
  shortened: PREVIEW.shortened,
}

function renderIt(handler: (call: Call) => unknown) {
  const calls = stubApi(handler)
  render(
    <QueryClientProvider client={new QueryClient()}>
      <SheetImportDialog />
    </QueryClientProvider>,
  )
  return calls
}

async function open(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole('button', { name: 'Import a company sheet' }))
  return screen.getByRole('dialog', { name: 'Import a company sheet' })
}

const sheetFile = () => new File(['Company\nAcme'], 'sheet.csv', { type: 'text/csv' })

afterEach(() => vi.unstubAllGlobals())

describe('SheetImportDialog', () => {
  it('US1 shows the columns used and ignored, the counts and the skipped rows', async () => {
    const user = userEvent.setup()
    const calls = renderIt((call) => (call.path === '/companies/sheet-import' ? PREVIEW : undefined))
    const dialog = await open(user)

    await user.upload(within(dialog).getByLabelText('Company sheet (CSV)'), sheetFile())

    const preview = await screen.findByRole('region', { name: 'Sheet preview' })
    expect(preview).toHaveTextContent('Columns used: name, location, contacts')
    expect(preview).toHaveTextContent('Ignored: Frontend openings, Budget')
    expect(preview).toHaveTextContent('3 companies already on your list, 2 to add')
    expect(preview).toHaveTextContent('12 contacts to add, 1 to update')
    expect(preview).toHaveTextContent('2 notes to set, 1 to change, 1 kept as you wrote it')
    const skipped = within(preview).getByRole('list', { name: 'Rows that will be skipped' })
    expect(skipped).toHaveTextContent('Row 9: The row has no company name.')
    expect(skipped).toHaveTextContent('Row 12: The row matches two companies')
    expect(preview).toHaveTextContent('Row 15: More than 20 people')
    expect(calls.some((c) => c.path.endsWith('/confirm'))).toBe(false) // nothing saved yet
  })

  it('US1 confirm shows the result summary after the import', async () => {
    const user = userEvent.setup()
    renderIt((call) => {
      if (call.path === '/companies/sheet-import') return PREVIEW
      if (call.path === '/companies/sheet-import/sheet123/confirm') return RESULT
      return undefined
    })
    const dialog = await open(user)
    await user.upload(within(dialog).getByLabelText('Company sheet (CSV)'), sheetFile())

    await user.click(await screen.findByRole('button', { name: 'Confirm import' }))

    const status = await screen.findByRole('status')
    expect(status).toHaveTextContent('2 companies added')
    expect(status).toHaveTextContent('12 contacts added, 1 updated')
    expect(status).toHaveTextContent('2 notes set, 1 changed, 1 kept')
    expect(status).toHaveTextContent('2 rows skipped')
    await waitFor(() => expect(screen.queryByRole('region', { name: 'Sheet preview' })).toBeNull())
  })

  it('US1 AS5 confirm is disabled while nothing would change', async () => {
    const user = userEvent.setup()
    renderIt((call) => (call.path === '/companies/sheet-import' ? NOTHING : undefined))
    const dialog = await open(user)

    await user.upload(within(dialog).getByLabelText('Company sheet (CSV)'), sheetFile())

    const preview = await screen.findByRole('region', { name: 'Sheet preview' })
    expect(preview).toHaveTextContent('Nothing to add or change.')
    expect(screen.getByRole('button', { name: 'Confirm import' })).toBeDisabled()
  })

  it('shows why a file was refused, with the headers it saw', async () => {
    const user = userEvent.setup()
    renderIt(() =>
      problem(422, 'Unprocessable', {
        detail: 'No column with a company name was found.',
        headers: ['Project', 'Owner'],
      }),
    )
    const dialog = await open(user)

    await user.upload(within(dialog).getByLabelText('Company sheet (CSV)'), sheetFile())

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('No column with a company name was found.')
    expect(alert).toHaveTextContent('Columns in the file: Project, Owner')
  })

  it('cancel leaves everything as it was', async () => {
    const user = userEvent.setup()
    const calls = renderIt((call) => (call.path === '/companies/sheet-import' ? PREVIEW : undefined))
    const dialog = await open(user)
    await user.upload(within(dialog).getByLabelText('Company sheet (CSV)'), sheetFile())

    await user.click(await screen.findByRole('button', { name: 'Cancel' }))

    expect(screen.queryByRole('dialog')).toBeNull()
    expect(calls.some((c) => c.path.endsWith('/confirm'))).toBe(false)
  })

  it('renders sheet text as plain text', async () => {
    const user = userEvent.setup()
    const hostile = {
      ...PREVIEW,
      skipped: [{ line: 2, reason: '<img src=x onerror=alert(1)> and <b>bold</b>' }],
    }
    renderIt((call) => (call.path === '/companies/sheet-import' ? hostile : undefined))
    const dialog = await open(user)

    await user.upload(within(dialog).getByLabelText('Company sheet (CSV)'), sheetFile())

    const preview = await screen.findByRole('region', { name: 'Sheet preview' })
    expect(preview).toHaveTextContent('<b>bold</b>')
    expect(preview.querySelector('img')).toBeNull()
    expect(preview.querySelector('b')).toBeNull()
  })
})
