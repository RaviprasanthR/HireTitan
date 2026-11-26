import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { GREETING_DELAY_MS, MikasaDock } from './MikasaDock'

function show() {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => new Response('null', { headers: { 'Content-Type': 'application/json' } })),
  )
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter>
        <MikasaDock />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('MikasaDock greeting', () => {
  beforeEach(() => {
    sessionStorage.clear()
    vi.useFakeTimers()
  })
  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it('asks if you need help a moment after the page opens, without taking the focus', () => {
    show()
    expect(screen.queryByRole('status', { name: 'Mikasa says' })).toBeNull()
    act(() => vi.advanceTimersByTime(GREETING_DELAY_MS))
    const bubble = screen.getByRole('status', { name: 'Mikasa says' })
    expect(bubble).toHaveTextContent('Need a hand with your job search?')
    expect(document.activeElement).toBe(document.body)
  })

  it('Yes opens the chat and the bubble goes', () => {
    show()
    act(() => vi.advanceTimersByTime(GREETING_DELAY_MS))
    fireEvent.click(screen.getByRole('button', { name: 'Yes, help me' }))
    expect(screen.getByRole('complementary', { name: 'Mikasa' })).toBeInTheDocument()
    expect(screen.queryByRole('status', { name: 'Mikasa says' })).toBeNull()
  })

  it('a dismissed greeting stays away for the rest of the visit', () => {
    show()
    act(() => vi.advanceTimersByTime(GREETING_DELAY_MS))
    fireEvent.click(screen.getByRole('button', { name: 'Not now' }))
    expect(screen.queryByRole('status', { name: 'Mikasa says' })).toBeNull()
    expect(sessionStorage.getItem('ht-mikasa-greeted')).toBe('1')
  })

  it('opening the chat from the button first means no greeting later', () => {
    show()
    fireEvent.click(screen.getByRole('button', { name: 'Mikasa' }))
    act(() => vi.advanceTimersByTime(GREETING_DELAY_MS))
    expect(screen.queryByRole('status', { name: 'Mikasa says' })).toBeNull()
  })
})
