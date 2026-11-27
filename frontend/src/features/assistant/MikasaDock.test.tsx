import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { GREETING_DELAY_MS, GREETING_SHOW_MS, GREETING_TYPING_MS, MikasaDock } from './MikasaDock'

const greet = () => act(() => vi.advanceTimersByTime(GREETING_DELAY_MS))
const typed = () => act(() => vi.advanceTimersByTime(GREETING_TYPING_MS))

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
    greet()
    const bubble = screen.getByRole('status', { name: 'Mikasa says' })
    // she types for a moment first, hopping to catch the eye, then the words arrive
    expect(bubble.querySelector('.mikasa-dot')).not.toBeNull()
    expect(bubble).not.toHaveTextContent('Need a hand')
    expect(document.querySelector('.ht-mikasa-hop')).not.toBeNull()
    typed()
    expect(bubble).toHaveTextContent('Need a hand with your job search?')
    expect(bubble).toHaveClass('ht-greeting-in')
    // no buttons (Ravi, 2026-11-26), in the contrasting Mikasa fill
    expect(bubble.querySelector('button')).toBeNull()
    expect(bubble).toHaveClass('ht-gradient-fill', 'text-primary-foreground')
    expect(document.activeElement).toBe(document.body)
  })

  it('a click on the bubble opens the chat and the bubble goes', () => {
    show()
    greet()
    typed()
    fireEvent.click(screen.getByRole('status', { name: 'Mikasa says' }))
    expect(screen.getByRole('complementary', { name: 'Mikasa' })).toBeInTheDocument()
    expect(screen.queryByRole('status', { name: 'Mikasa says' })).toBeNull()
  })

  it('left alone, the bubble fades out by itself and stays away for the rest of the visit', () => {
    show()
    greet()
    typed()
    act(() => vi.advanceTimersByTime(GREETING_SHOW_MS))
    expect(screen.getByRole('status', { name: 'Mikasa says' })).toHaveClass('ht-greeting-out')
    act(() => vi.advanceTimersByTime(300))
    expect(screen.queryByRole('status', { name: 'Mikasa says' })).toBeNull()
    expect(sessionStorage.getItem('ht-mikasa-greeted')).toBe('1')
  })

  it('closing the chat again does not bring the bubble back', () => {
    show()
    greet()
    typed()
    fireEvent.click(screen.getByRole('status', { name: 'Mikasa says' }))
    fireEvent.click(screen.getByRole('button', { name: /close/i }))
    expect(screen.queryByRole('status', { name: 'Mikasa says' })).toBeNull()
  })

  it('opening the chat moves focus into it', () => {
    show()
    fireEvent.click(screen.getByRole('button', { name: 'Mikasa' }))
    expect(document.activeElement).toBe(screen.getByRole('heading', { name: 'Mikasa' }))
  })

  it('opening the chat from the button first means no greeting later', () => {
    show()
    fireEvent.click(screen.getByRole('button', { name: 'Mikasa' }))
    act(() => vi.advanceTimersByTime(GREETING_DELAY_MS))
    expect(screen.queryByRole('status', { name: 'Mikasa says' })).toBeNull()
  })
})
