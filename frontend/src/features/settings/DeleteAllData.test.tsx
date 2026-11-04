import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { DeleteAllData } from './DeleteAllData'

let calls: { method: string; url: string; body?: string }[]
let reply: () => Response

beforeEach(() => {
  calls = []
  reply = () => new Response(null, { status: 204 })
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      calls.push({ method: init?.method ?? 'GET', url, body: init?.body as string | undefined })
      return reply()
    }),
  )
})
afterEach(() => vi.unstubAllGlobals())

function renderZone() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const invalidate = vi.spyOn(client, 'invalidateQueries')
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/settings']}>
        <Routes>
          <Route path="/settings" element={<DeleteAllData />} />
          <Route path="/" element={<p>Home</p>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
  return { invalidate }
}

async function openDialog() {
  await userEvent.click(screen.getByRole('button', { name: 'Delete all my data' }))
  return screen.getByRole('alertdialog')
}

describe('DeleteAllData', () => {
  it('US4_AS2_requires_typed_word', async () => {
    renderZone()
    await openDialog()
    const confirm = screen.getByRole('button', { name: 'Delete everything' })
    expect(confirm).toBeDisabled()

    await userEvent.type(screen.getByLabelText(/type DELETE/i), 'delete')
    expect(confirm).toBeDisabled()

    await userEvent.clear(screen.getByLabelText(/type DELETE/i))
    await userEvent.type(screen.getByLabelText(/type DELETE/i), 'DELETE')
    expect(confirm).toBeEnabled()
    expect(calls).toEqual([])
  })

  it('sends the confirmation word, then goes back to the start', async () => {
    const { invalidate } = renderZone()
    await openDialog()
    await userEvent.type(screen.getByLabelText(/type DELETE/i), 'DELETE')
    await userEvent.click(screen.getByRole('button', { name: 'Delete everything' }))

    expect(await screen.findByText('Home')).toBeInTheDocument()
    expect(calls).toEqual([
      { method: 'POST', url: '/api/v1/data/delete-all', body: JSON.stringify({ confirm: 'DELETE' }) },
    ])
    expect(invalidate).toHaveBeenCalled()
  })

  it('keeps the dialog open and shows the error when it fails', async () => {
    reply = () =>
      new Response(JSON.stringify({ title: 'Failed', detail: 'Could not delete.' }), {
        status: 500,
        headers: { 'Content-Type': 'application/problem+json' },
      })
    renderZone()
    await openDialog()
    await userEvent.type(screen.getByLabelText(/type DELETE/i), 'DELETE')
    await userEvent.click(screen.getByRole('button', { name: 'Delete everything' }))

    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Could not delete.'))
    expect(screen.getByRole('alertdialog')).toBeInTheDocument()
  })

  it('Cancel closes the dialog without deleting', async () => {
    renderZone()
    await openDialog()
    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    await waitFor(() => expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument())
    expect(calls).toEqual([])
  })
})
