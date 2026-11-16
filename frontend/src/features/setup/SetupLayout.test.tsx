import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { describe, expect, it } from 'vitest'
import { SetupLayout } from './SetupLayout'
import { stubApi } from '@/test/api'

const client = new QueryClient({
  defaultOptions: { queries: { retry: false } },
})
const wrap = (ui: React.ReactNode) => (
  <QueryClientProvider client={client}>
    <MemoryRouter>{ui}</MemoryRouter>
  </QueryClientProvider>
)

describe('SetupLayout', () => {
  it('keeps the logo turning through the setup steps and stops when they end', () => {
    stubApi(() => ({}))
    const { rerender, unmount } = render(wrap(<SetupLayout step={2}>x</SetupLayout>))
    expect(document.documentElement).toHaveAttribute('data-working')
    rerender(wrap(<SetupLayout>x</SetupLayout>))
    expect(document.documentElement).not.toHaveAttribute('data-working')
    unmount()
  })
})
