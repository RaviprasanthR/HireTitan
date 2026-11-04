import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { App } from './App'

describe('App', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('renders_app_root', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => {
        const body = String(url).endsWith('/onboarding')
          ? { step: 'done', display_name: 'Jane', open_review_id: null, active_run_id: null }
          : []
        return new Response(JSON.stringify(body), { headers: { 'Content-Type': 'application/json' } })
      }),
    )
    render(<App />)
    expect(await screen.findByTestId('app-root')).toBeInTheDocument()
    expect(screen.getByText('HireTitan')).toBeInTheDocument()
  })
})
