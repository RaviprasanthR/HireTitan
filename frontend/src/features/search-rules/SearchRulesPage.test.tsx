import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { SearchRulesPage } from './SearchRulesPage'

const json = (body: unknown, status = 200, type = 'application/json') =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': type } })

type Item = { text: string; origin: string; effect: string }

function rules(overrides: Record<string, unknown> = {}) {
  return {
    title_words: [
      { text: 'Backend Engineer', origin: 'preference:target_roles[0]', effect: 'skips' },
      { text: 'backend developer', origin: 'synonym_table', effect: 'skips' },
    ] as Item[],
    title_avoid: [{ text: 'frontend', origin: 'area:front_end', effect: 'skips' }] as Item[],
    blocked_locations: [
      { city: 'Pune', country: 'IN', origin: 'preference:blocked_locations[0]', effect: 'skips' },
    ],
    max_age_days: 30,
    stack_keywords: [{ text: 'Python', origin: 'profile:skills', effect: 'guides_ai' }] as Item[],
    preferred_locations: [],
    work_modes: ['remote'],
    seniority: [],
    years_experience: '4.5',
    areas: ['back_end'],
    ...overrides,
  }
}

function approvedSet(over: Record<string, unknown> = {}) {
  return {
    id: 'a1',
    version: 1,
    status: 'approved',
    rules: rules(),
    based_on: {},
    approved_at: '2026-11-05T10:00:00Z',
    approved_by: 'person',
    ...over,
  }
}

type State = { approved: unknown; proposal: unknown; stale: boolean }
let state: State
let calls: { method: string; path: string; body?: string }[]
let suggested: ReturnType<typeof rules>
let saveReply: (() => Response) | null

function serve() {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? 'GET'
      const path = url.replace('/api/v1', '')
      calls.push({ method, path, body: init?.body as string | undefined })
      if (method === 'GET' && path === '/search/rules/suggested') return json(suggested)
      if (method === 'GET' && path === '/search/rules') return json(state)
      if (method === 'PUT' && path === '/search/rules/approved') {
        if (saveReply) return saveReply()
        const sent = JSON.parse(init?.body as string)
        const next = approvedSet({ id: 'a2', version: 2, rules: sent })
        state = { approved: next, proposal: null, stale: false }
        return json(next)
      }
      if (method === 'DELETE' && path === '/search/rules/proposal') {
        state = { ...state, proposal: null }
        return new Response(null, { status: 204 })
      }
      return new Response(null, { status: 404 })
    }),
  )
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <SearchRulesPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  state = { approved: approvedSet(), proposal: null, stale: false }
  suggested = rules({ title_words: [{ text: 'Suggested Engineer', origin: 'user', effect: 'skips' }] })
  saveReply = null
  calls = []
  serve()
})
afterEach(() => vi.unstubAllGlobals())

const OLD_TAGS = [
  'Skips jobs',
  'Guides the AI',
  'Similar title',
  'From your preferences',
  'From your profile',
  'Added by you',
]

async function openEditor(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByRole('button', { name: /edit rules/i }))
}

describe('SearchRulesPage', () => {
  it('US3_AS1_shows_the_three_groups_in_plain_language', async () => {
    renderPage()

    const keep = await screen.findByRole('region', { name: 'Jobs we keep' })
    expect(within(keep).getByText('Backend Engineer')).toBeInTheDocument()
    const leave = screen.getByRole('region', { name: 'Jobs we leave out' })
    expect(within(leave).getByText('frontend')).toBeInTheDocument()
    expect(within(leave).getByText('Pune, IN')).toBeInTheDocument()
    expect(within(leave).getByText('30 days')).toBeInTheDocument()
    const rank = screen.getByRole('region', { name: 'What helps rank a job' })
    expect(within(rank).getByText('Back end')).toBeInTheDocument() // the area, as a person says it
    expect(within(rank).getByText('Python')).toBeInTheDocument()
    expect(within(rank).getByText(/Years of experience: 4\.5/)).toBeInTheDocument()
    expect(within(rank).getByRole('link', { name: /change these in preferences/i })).toHaveAttribute(
      'href',
      '/profile/preferences',
    )
  })

  it('SC003_shows_none_of_the_old_tag_texts', async () => {
    renderPage()
    await screen.findByRole('region', { name: 'Jobs we keep' })
    for (const tag of OLD_TAGS) expect(document.body.textContent).not.toContain(tag)
    expect(document.body.textContent).not.toMatch(/area:front_end|synonym_table|preference:/)
  })

  it('US1_AS2_FR020_says_the_rules_were_set_up_automatically', async () => {
    state = { approved: approvedSet({ approved_by: 'auto' }), proposal: null, stale: false }
    renderPage()
    expect(
      await screen.findByText(/HireTitan set these up from your profile and preferences/i),
    ).toBeInTheDocument()
  })

  it('FR020_says_nothing_about_rules_the_person_approved', async () => {
    renderPage()
    await screen.findByText(/These are the rules your searches use/i)
    expect(screen.queryByText(/HireTitan set these up/i)).not.toBeInTheDocument()
  })

  it('US3_AS3_edit_and_save_makes_a_new_version', async () => {
    const user = userEvent.setup()
    renderPage()

    await openEditor(user)
    await user.type(screen.getByLabelText('Job titles'), 'Platform Engineer{Enter}')
    await user.click(screen.getByRole('button', { name: 'Save rules' }))

    expect(await screen.findByText('Rules saved.')).toBeInTheDocument()
    const put = calls.find((c) => c.method === 'PUT')
    expect(put?.path).toBe('/search/rules/approved')
    const sent = JSON.parse(put?.body as string)
    expect(sent.title_words.map((i: Item) => i.text)).toEqual([
      'Backend Engineer',
      'backend developer',
      'Platform Engineer',
    ])
    // the person's untouched rules keep their origin; the new one is the person's own
    expect(sent.title_words[0].origin).toBe('preference:target_roles[0]')
    expect(sent.title_words[2].origin).toBe('user')
    expect(screen.getByText(/version 2/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Save rules' })).not.toBeInTheDocument()
  })

  it('SC004_changing_a_title_takes_three_clicks_or_fewer', async () => {
    const user = userEvent.setup()
    renderPage()
    let clicks = 0
    document.addEventListener('click', () => (clicks += 1), true)

    await openEditor(user) // click 1 (Edit)
    await user.type(screen.getByLabelText('Job titles'), 'Platform Engineer{Enter}')
    await user.click(screen.getByRole('button', { name: 'Save rules' })) // click 2 (Save)

    await screen.findByText('Rules saved.')
    expect(clicks).toBeLessThanOrEqual(3)
  })

  it('US3_AS4_cancel_changes_nothing', async () => {
    const user = userEvent.setup()
    renderPage()

    await openEditor(user)
    await user.type(screen.getByLabelText('Job titles'), 'Platform Engineer{Enter}')
    await user.click(screen.getByRole('button', { name: 'Cancel' }))

    expect(calls.some((c) => c.method === 'PUT')).toBe(false)
    const keep = await screen.findByRole('region', { name: 'Jobs we keep' })
    expect(within(keep).queryByText('Platform Engineer')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /edit rules/i })).toBeInTheDocument()
  })

  it('US3_AS5_invalid_save_shows_the_error_next_to_its_group', async () => {
    const user = userEvent.setup()
    saveReply = () =>
      json(
        {
          title: 'Some fields are not valid.',
          status: 422,
          errors: [
            { field: 'title_words', message: 'Add at least 1.' },
            { field: 'max_age_days', message: 'Use a number from 1 to 365.' },
          ],
        },
        422,
        'application/problem+json',
      )
    renderPage()

    await openEditor(user)
    await user.click(screen.getByRole('button', { name: 'Save rules' }))

    const keep = await screen.findByRole('region', { name: 'Jobs we keep' })
    expect(await within(keep).findByRole('alert')).toHaveTextContent('Add at least one job title.')
    const leave = screen.getByRole('region', { name: 'Jobs we leave out' })
    expect(within(leave).getByRole('alert')).toHaveTextContent('Use a number of days from 1 to 365.')
    expect(screen.getByRole('button', { name: 'Save rules' })).toBeEnabled() // still editing
  })

  it('US3_AS6_update_from_my_profile_opens_suggested_rules_unsaved', async () => {
    const user = userEvent.setup()
    state = { approved: approvedSet(), proposal: null, stale: true }
    renderPage()

    expect(await screen.findByText(/changed since these rules were set/i)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Update from my profile' }))

    expect(await screen.findByText('Suggested Engineer')).toBeInTheDocument() // in the editor
    expect(screen.getByRole('button', { name: 'Save rules' })).toBeInTheDocument()
    expect(calls.some((c) => c.method === 'PUT')).toBe(false) // nothing changed yet
  })

  it('US3_AS7_start_over_fills_the_editor_with_suggested_rules_unsaved', async () => {
    const user = userEvent.setup()
    renderPage()

    await openEditor(user)
    await user.click(screen.getByRole('button', { name: /start over with suggested rules/i }))

    expect(await screen.findByText('Suggested Engineer')).toBeInTheDocument()
    expect(screen.queryByText('Backend Engineer')).not.toBeInTheDocument()
    expect(calls.some((c) => c.method === 'PUT')).toBe(false)
  })

  it('US3_AS8_asks_before_leaving_with_unsaved_edits', async () => {
    const user = userEvent.setup()
    renderPage()
    await openEditor(user)

    const untouched = new Event('beforeunload', { cancelable: true })
    window.dispatchEvent(untouched)
    expect(untouched.defaultPrevented).toBe(false) // nothing changed: no question

    await user.type(screen.getByLabelText('Job titles'), 'Platform Engineer{Enter}')
    const changed = new Event('beforeunload', { cancelable: true })
    window.dispatchEvent(changed)
    expect(changed.defaultPrevented).toBe(true)
  })

  it('leftover_proposal_opens_in_the_editor_and_cancel_discards_it', async () => {
    const user = userEvent.setup()
    state = {
      approved: approvedSet(),
      proposal: approvedSet({
        id: 'p1',
        version: 2,
        status: 'proposed',
        approved_at: null,
        approved_by: null,
        rules: rules({ title_words: [{ text: 'Half Done', origin: 'user', effect: 'skips' }] }),
      }),
      stale: false,
    }
    renderPage()

    expect(await screen.findByText('Half Done')).toBeInTheDocument()
    expect(screen.getByText(/you had changes in progress/i)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Cancel' }))

    await waitFor(() =>
      expect(calls.some((c) => c.method === 'DELETE' && c.path === '/search/rules/proposal')).toBe(
        true,
      ),
    )
    expect(await screen.findByRole('button', { name: /edit rules/i })).toBeInTheDocument()
  })

  it('areas_can_be_picked_up_to_four', async () => {
    const user = userEvent.setup()
    state = { approved: approvedSet({ rules: rules({ areas: ['back_end'] }) }), proposal: null, stale: false }
    renderPage()
    await openEditor(user)

    for (const name of ['Front end', 'Mobile', 'Data']) {
      await user.click(screen.getByRole('checkbox', { name }))
    }

    expect(screen.getByRole('checkbox', { name: 'QA and testing' })).toBeDisabled() // a fifth
    expect(screen.getByRole('checkbox', { name: 'Back end' })).toBeEnabled() // can be unchecked
  })

  it('without_approved_rules_the_person_can_get_suggestions_and_save', async () => {
    const user = userEvent.setup()
    state = { approved: null, proposal: null, stale: false }
    renderPage()

    await user.click(await screen.findByRole('button', { name: 'Suggest rules' }))
    expect(await screen.findByText('Suggested Engineer')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Save rules' }))

    await waitFor(() => expect(calls.some((c) => c.method === 'PUT')).toBe(true))
  })
})
