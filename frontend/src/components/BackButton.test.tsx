import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { RouterProvider, createMemoryRouter } from 'react-router'
import { describe, expect, it } from 'vitest'
import { BackButton } from './BackButton'

function renderAt(entries: string[]) {
  const router = createMemoryRouter(
    [
      { path: '/explore', element: <p>Explore page</p> },
      { path: '/search/history', element: <p>History page</p> },
      { path: '/search/runs/:id', element: <BackButton fallback="/search/history" /> },
      { path: '/search/fixed', element: <BackButton to="/explore" /> },
    ],
    { initialEntries: entries, initialIndex: entries.length - 1 },
  )
  render(<RouterProvider router={router} />)
}

describe('BackButton', () => {
  it('goes back to the page the person came from', async () => {
    renderAt(['/explore', '/search/runs/r1'])
    await userEvent.click(screen.getByRole('button', { name: 'Back' }))
    expect(await screen.findByText('Explore page')).toBeInTheDocument()
  })

  it('goes to the fallback page when opened directly', async () => {
    renderAt(['/search/runs/r1'])
    await userEvent.click(screen.getByRole('button', { name: 'Back' }))
    expect(await screen.findByText('History page')).toBeInTheDocument()
  })

  it('always goes to its page when one is given', async () => {
    renderAt(['/search/history', '/search/fixed'])
    await userEvent.click(screen.getByRole('button', { name: 'Back' }))
    expect(await screen.findByText('Explore page')).toBeInTheDocument()
  })
})
