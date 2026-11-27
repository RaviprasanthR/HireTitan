import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { STATUS, stubApi } from '@/test/api'
import { SettingsPage } from './SettingsPage'

function renderPage(keySource = 'page', keyStatus = 'working', at = '/settings') {
  stubApi((call) => {
    if (call.path === '/status')
      return { ...STATUS, ai: { ...STATUS.ai, status: keyStatus, key_source: keySource } }
    if (call.path === '/mail/connection')
      return {
        state: 'not_connected',
        address: null,
        credentials_set: false,
        credentials_from_environment: false,
        redirect_uri: 'http://localhost:8000/api/v1/mail/google/callback',
        last_check_started_at: null,
        last_error: null,
        window_hours: 24,
      }
    return undefined
  })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[at]}>
        <Routes>
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/settings/:tab" element={<SettingsPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

afterEach(() => vi.unstubAllGlobals())

describe('SettingsPage (US6)', () => {
  it('US6 AS1 three tabs, like Home: AI, Gmail job alerts, Your data', async () => {
    renderPage()

    const tabs = await screen.findByRole('navigation', { name: 'Settings tabs' })
    expect(within(tabs).getAllByRole('link').map((l) => [l.textContent, l.getAttribute('href')])).toEqual([
      ['AI', '/settings/ai'],
      ['Gmail job alerts', '/settings/gmail'],
      ['Your data', '/settings/data'],
    ])
  })

  it('test_FR017_settings_uses_full_width', async () => {
    renderPage()
    const tabs = await screen.findByRole('navigation', { name: 'Settings tabs' })
    const page = tabs.closest('section') as HTMLElement
    // no narrow column inside the page, and the AI card has no stripe of its own
    expect(page.querySelector('[class*="max-w-3xl"], [class*="max-w-2xl"]')).toBeNull()
    expect(page.querySelector('.ht-settings-ai')).toBeNull()
  })

  it('US6 AS1 plain Settings opens the AI tab', async () => {
    renderPage()

    expect(await screen.findByRole('heading', { level: 2, name: 'AI' })).toBeInTheDocument()
    expect(screen.getByText(/reads resumes, checks jobs/)).toBeInTheDocument()
    expect(screen.queryByRole('heading', { level: 2, name: 'Gmail job alerts' })).not.toBeInTheDocument()
    expect(within(screen.getByRole('navigation', { name: 'Settings tabs' })).getByRole('link', { name: 'AI' })).toHaveClass('border-link')
  })

  it('a tab is its own address', async () => {
    renderPage('page', 'working', '/settings/gmail')

    expect(await screen.findByRole('heading', { level: 2, name: 'Gmail job alerts' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { level: 2, name: 'AI' })).not.toBeInTheDocument()
  })

  it('coming back from Google opens the Gmail tab', async () => {
    renderPage('page', 'working', '/settings?gmail=connected')

    expect(await screen.findByRole('heading', { level: 2, name: 'Gmail job alerts' })).toBeInTheDocument()
  })

  it('an unknown tab opens AI', async () => {
    renderPage('page', 'working', '/settings/nothing')

    expect(await screen.findByRole('heading', { level: 2, name: 'AI' })).toBeInTheDocument()
  })

  it('US6 AS2 with no key the AI tab offers a key field', async () => {
    renderPage('none', 'missing')

    expect(await screen.findByLabelText('OpenAI API key')).toBeInTheDocument()
    expect(screen.getByText('Missing')).toBeInTheDocument()
  })

  it('US6 AS7 Your data has delete all with its warning', async () => {
    renderPage('page', 'working', '/settings/data')

    const data = await screen.findByRole('region', { name: 'Your data' })
    expect(within(data).getByText(/Remove everything HireTitan holds/)).toBeInTheDocument()
    expect(within(data).getByRole('button', { name: /delete all my data/i })).toBeInTheDocument()
  })
})
