import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { HomePage } from './HomePage'

const json = (body: unknown) =>
  new Response(JSON.stringify(body), {
    headers: { 'Content-Type': 'application/json' },
  })

function renderHome(checklist: Record<string, boolean>, displayName: string | null = 'Jane') {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) =>
      String(url).endsWith('/onboarding')
        ? json({
            step: 'done',
            display_name: displayName,
            open_review_id: null,
            active_run_id: null,
          })
        : json({
            ai: {
              provider: 'openai',
              status: 'working',
              message: null,
              checked_at: null,
            },
            checklist,
            budget: { cap_usd: '25.00', spent_usd: '0', period: '2026-11' },
          }),
    ),
  )
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <HomePage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

const none = {
  key_ok: false,
  resume_uploaded: false,
  profile_confirmed: false,
  preferences_saved: false,
  rules_approved: false,
  searched_once: false,
}

describe('HomePage', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('FR028_checklist_links', async () => {
    renderHome({ ...none, key_ok: true })
    const list = await screen.findByRole('list', { name: 'Setup checklist' })
    const steps = within(list).getAllByRole('listitem')
    expect(steps).toHaveLength(5)

    const key = steps[0] as HTMLElement
    expect(key).toHaveTextContent('AI key found and working')
    expect(key).toHaveTextContent('Done')
    expect(within(key).queryByRole('link')).not.toBeInTheDocument() // nothing left to do

    expect(
      within(steps[1] as HTMLElement).getByRole('link', {
        name: 'Upload your resume',
      }),
    ).toHaveAttribute('href', '/profile')
    expect(steps[1]).toHaveTextContent('To do')
    expect(
      within(steps[2] as HTMLElement).getByRole('link', {
        name: 'Confirm your profile',
      }),
    ).toHaveAttribute('href', '/profile')
  })

  it('missing_key_links_to_settings', async () => {
    renderHome(none)
    expect(await screen.findByRole('link', { name: 'Check the AI key' })).toHaveAttribute(
      'href',
      '/settings',
    )
  })

  it('preferences_wait_for_a_confirmed_profile', async () => {
    renderHome({ ...none, resume_uploaded: true })
    const list = await screen.findByRole('list', { name: 'Setup checklist' })
    const prefs = within(list).getAllByRole('listitem')[3] as HTMLElement
    expect(within(prefs).queryByRole('link')).not.toBeInTheDocument()
    expect(prefs).toHaveTextContent('after you confirm your profile')
  })

  it('preferences_link_once_the_profile_is_confirmed', async () => {
    renderHome({ ...none, resume_uploaded: true, profile_confirmed: true })
    expect(await screen.findByRole('link', { name: 'Set your preferences' })).toHaveAttribute(
      'href',
      '/preferences',
    )
  })

  it('all_done', async () => {
    renderHome({
      key_ok: true,
      resume_uploaded: true,
      profile_confirmed: true,
      preferences_saved: true,
      rules_approved: true,
      searched_once: false,
    })
    expect(await screen.findByText('You are all set up.')).toBeInTheDocument()
    expect(screen.queryByRole('link')).not.toBeInTheDocument()
  })

  it('US2_search_rules_step_waits_for_preferences_then_links', async () => {
    renderHome({ ...none, resume_uploaded: true, profile_confirmed: true })
    const list = await screen.findByRole('list', { name: 'Setup checklist' })
    const rules = within(list).getAllByRole('listitem')[4] as HTMLElement
    expect(rules).toHaveTextContent('after you save your preferences')
    expect(within(rules).queryByRole('link')).not.toBeInTheDocument()
  })

  it('US2_search_rules_step_links_once_preferences_are_saved', async () => {
    renderHome({
      ...none,
      resume_uploaded: true,
      profile_confirmed: true,
      preferences_saved: true,
    })
    expect(await screen.findByRole('link', { name: 'Review your search rules' })).toHaveAttribute(
      'href',
      '/search/rules',
    )
  })

  it('US5_AS7_greets_by_name', async () => {
    renderHome(none, 'Jane')
    expect(await screen.findByText('Welcome back, Jane')).toBeInTheDocument()
  })

  it('greets_without_a_name', async () => {
    renderHome(none, null)
    await screen.findByRole('list', { name: 'Setup checklist' })
    expect(screen.queryByText(/Welcome back/)).not.toBeInTheDocument()
  })
})
