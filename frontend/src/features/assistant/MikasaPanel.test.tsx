import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { CONVERSATION_KEY, MikasaPanel } from './MikasaPanel'

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function sse(pieces: string[], hold?: Promise<void>) {
  const encoder = new TextEncoder()
  return new Response(
    new ReadableStream({
      async start(controller) {
        for (const piece of pieces) controller.enqueue(encoder.encode(piece))
        if (hold) await hold
        controller.close()
      },
    }),
    { status: 200, headers: { 'Content-Type': 'text/event-stream' } },
  )
}

let status: unknown
let stored: unknown[]
let turn: (init: RequestInit) => Response | Promise<Response>

function stubApi() {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init: RequestInit = {}) => {
      if (url.endsWith('/assistant/status')) return json(status)
      if (url.endsWith('/assistant/quick-actions')) return json(QUICK)
      if (url.includes('/staged')) {
        if (init.method !== 'POST') return json(stagedNow)
        const name = url.split('/staged/')[1] ?? ''
        const body = init.body ? JSON.parse(String(init.body)) : null
        if (stagedRefusal) return json({ detail: stagedRefusal, status: 422 }, 422)
        staged.push({ name, body })
        stagedUrls.push(url)
        const held = {
          label: 'Platform Engineer at Initech',
          job_ref: 'job:j9',
          already_saved: false,
        }
        if (name === 'begin')
          stagedNow = {
            step: 'need_post',
            kind: body.kind,
            label: null,
            job_ref: null,
            draft_ref: null,
            already_saved: false,
          }
        if (name === 'post') stagedNow = { ...held, step: 'need_kind', kind: null, draft_ref: null }
        if (name === 'details')
          stagedNow = { ...held, step: 'need_kind', kind: null, draft_ref: null }
        if (name === 'choose')
          stagedNow = { ...held, step: 'ask_save', kind: body.kind, draft_ref: 'draft:d1' }
        if (name === 'save' || name === 'discard') stagedNow = null
        return name === 'save' ? json({ summary: 'Saved.' }) : json(stagedNow)
      }
      if (url.includes('/assistant/refs/'))
        return json({
          ref: 'draft:d1',
          kind: 'draft',
          title: 'Email',
          subtitle: 'For Hiring team',
          lines: ['Hi there, I would love to talk.'],
          link: '/jobs/j9',
        })
      if (url.includes('/jobs?list=')) return json({ items: JOBS, next_cursor: null })
      if (url.includes('/quick/status')) {
        quick.push({ url, body: JSON.parse(String(init.body)) })
        return json({ message_id: 'm9', text: 'Marked applied.', refs: [], changes: [], cards: [] })
      }
      if (url.includes('/quick/draft')) {
        if (draftRefusal) return json({ detail: draftRefusal, status: 409 }, 409)
        quick.push({ url, body: JSON.parse(String(init.body)) })
        return json({ message_id: 'm9', draft_id: 'd1', text: 'Writing', refs: [] })
      }
      if (url.endsWith('/assistant/conversations') && init.method === 'POST')
        return json({ id: 'c1' }, 201)
      if (url.endsWith('/assistant/conversations')) return json([])
      if (url.endsWith('/messages')) return json(stored)
      if (url.endsWith('/turns')) return turn(init)
      return json({}, 404)
    }),
  )
}

const QUICK = [
  {
    key: 'linkedin_request',
    label: 'LinkedIn connection message',
    form: 'draft',
    draft_kind: 'connection_request',
  },
  {
    key: 'linkedin_message',
    label: 'LinkedIn message',
    form: 'draft',
    draft_kind: 'referral_message',
  },
  { key: 'email', label: 'Email', form: 'draft', draft_kind: 'email' },
  { key: 'update_status', label: "Update a job's status", form: 'status', draft_kind: null },
  { key: 'add_job', label: 'Add a job', form: 'paste', draft_kind: null },
]
const JOBS = [
  { id: 'j1', title: 'Backend Engineer', company_name: 'Acme', state: 'explore' },
  { id: 'j2', title: 'Data Engineer', company_name: 'Globex', state: 'applied' },
]
let quick: { url: string; body: unknown }[] = []
let staged: { name: string; body: unknown }[] = []
let stagedUrls: string[] = []
let stagedNow: unknown = null
let stagedRefusal: string | null = null
let draftRefusal: string | null = null

/** The text box opens only when asked for (FR-029). */
async function openTextBox(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByRole('button', { name: 'Ask something else' }))
}

function show(onClose = () => {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/companies']}>
        <main>The page</main>
        <MikasaPanel onClose={onClose} />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('MikasaPanel', () => {
  beforeEach(() => {
    localStorage.clear()
    status = { available: true, reason: null, provider_message: null }
    stored = []
    quick = []
    staged = []
    stagedUrls = []
    stagedNow = null
    stagedRefusal = null
    draftRefusal = null
    turn = () => sse([])
    stubApi()
  })
  afterEach(() => vi.unstubAllGlobals())

  it('US1_AS1_panel_opens_beside_page', async () => {
    show()
    expect(screen.getByRole('complementary', { name: 'Mikasa' })).toBeInTheDocument()
    expect(screen.getByText('The page')).toBeInTheDocument() // the page stays
    expect(await screen.findByText(/Ask me about your jobs/)).toBeInTheDocument()
  })

  it('test_US3_AS6_avatar_is_flat', async () => {
    show()
    const panel = screen.getByRole('complementary', { name: 'Mikasa' })
    const avatar = panel.querySelector('header [aria-hidden].rounded-full') as HTMLElement
    expect(avatar).toHaveClass('bg-primary')
    expect(avatar.className).not.toMatch(/gradient|shadow/)
    // the panel: one neutral shadow from the tokens, not a border plus a soft shadow
    expect(panel).toHaveClass('shadow-[var(--ht-shadow-overlay)]')
    expect(panel.className).not.toMatch(/(^|\s)border(\s|$)|shadow-2xl|shadow-black/)
    // nothing in the panel uses raw white borders instead of the hairline tokens
    expect(panel.querySelector('[class*="border-white"]')).toBeNull()
  })

  it('FR022b_privacy_note_shown', async () => {
    show()
    await openTextBox(userEvent.setup())
    expect(
      screen.getByText(/What you type here is sent to your AI provider\. Contacts, notes/),
    ).toBeInTheDocument()
  })

  it('FR024_unavailable_message', async () => {
    status = { available: false, reason: 'out_of_credit', provider_message: 'Quota exceeded' }
    show()
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('out of credit')
    expect(alert).toHaveTextContent('Quota exceeded')
    expect(screen.getByRole('link', { name: 'Open Settings' })).toHaveAttribute('href', '/settings')
    await userEvent.setup().click(screen.getByRole('button', { name: 'Ask something else' }))
    expect(screen.getByLabelText('Message to Mikasa')).toBeDisabled()
  })

  it('US1_AS5_text_streams_and_stop', async () => {
    let release = () => {}
    const hold = new Promise<void>((resolve) => (release = resolve))
    let sent: RequestInit | undefined
    turn = (init) => {
      sent = init
      return sse(['event: text\ndata: {"delta": "Two jobs"}\n\n'], hold)
    }
    const user = userEvent.setup()
    show()
    await screen.findByText(/Ask me about your jobs/)
    await openTextBox(user)

    await user.type(screen.getByLabelText('Message to Mikasa'), 'What did I apply to?{Enter}')

    expect(await screen.findByTestId('live-reply')).toHaveTextContent('Two jobs')
    expect(JSON.parse(String(sent?.body))).toEqual({
      text: 'What did I apply to?',
      page: '/companies',
    })
    expect(localStorage.getItem(CONVERSATION_KEY)).toBe('c1')
    await user.click(screen.getByRole('button', { name: 'Stop' }))
    release()
    await waitFor(() => expect(screen.queryByTestId('live-reply')).not.toBeInTheDocument())
  })

  it('FR001_panel_on_every_page_keeps_conversation', async () => {
    localStorage.setItem(CONVERSATION_KEY, 'c9')
    stored = [
      {
        id: 'm1',
        seq: 1,
        author: 'person',
        text: 'Hello',
        status: 'complete',
        refs: [],
        signals: [],
        error: null,
        created_at: '',
      },
      {
        id: 'm2',
        seq: 2,
        author: 'mikasa',
        text: 'Hi there',
        status: 'complete',
        refs: [],
        signals: [],
        error: null,
        created_at: '',
      },
    ]
    const onClose = vi.fn()
    const user = userEvent.setup()
    show(onClose)

    expect(await screen.findByText('Hi there')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Close Mikasa' }))
    expect(onClose).toHaveBeenCalled()
    expect(localStorage.getItem(CONVERSATION_KEY)).toBe('c9')
  })

  it('counts characters and stops at 2,000', async () => {
    const user = userEvent.setup()
    show()
    await screen.findByText(/Ask me about your jobs/)
    await openTextBox(user)
    const box = screen.getByLabelText('Message to Mikasa')
    await user.click(box)
    await user.paste('x'.repeat(2001))
    expect(screen.getByText('2001 / 2000')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled()
  })

  it('FR021_paste_from_composer', async () => {
    let pasted: unknown = null
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string, init: RequestInit = {}) => {
        if (url.endsWith('/assistant/status')) return json(status)
        if (url.endsWith('/assistant/quick-actions')) return json(QUICK)
        if (url.endsWith('/assistant/conversations') && init.method === 'POST')
          return json({ id: 'c1' }, 201)
        if (url.endsWith('/assistant/conversations')) return json([])
        if (url.endsWith('/messages')) return json([])
        if (url.endsWith('/paste')) {
          pasted = JSON.parse(String(init.body))
          return json({ summary: 'Added Backend Engineer at Acme.', change_id: 'x1' }, 201)
        }
        return json({}, 404)
      }),
    )
    const user = userEvent.setup()
    show()
    await screen.findByText(/Ask me about your jobs/)

    await user.click(await screen.findByRole('button', { name: 'Add a job' }))
    const form = screen.getByRole('form', { name: 'Paste a job description' })
    expect(form).toHaveTextContent('never sent to the AI')
    await user.type(screen.getByLabelText('Link to the job'), 'https://jobs.example.com/1')
    await user.click(screen.getByLabelText('Job description'))
    await user.paste('We build payment APIs in Python. You will own services end to end.')
    await user.click(screen.getByRole('button', { name: 'Save job' }))

    await waitFor(() => expect(pasted).not.toBeNull())
    expect(pasted).toEqual({
      url: 'https://jobs.example.com/1',
      description: 'We build payment APIs in Python. You will own services end to end.',
    })
    await waitFor(() =>
      expect(
        screen.queryByRole('form', { name: 'Paste a job description' }),
      ).not.toBeInTheDocument(),
    )
  })

  it('FR029_quick_actions_first', async () => {
    show()

    for (const name of [
      'LinkedIn connection message',
      'LinkedIn message',
      'Email',
      "Update a job's status",
      'Add a job',
    ])
      expect(await screen.findByRole('button', { name })).toBeVisible()
    expect(screen.queryByLabelText('Message to Mikasa')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Ask something else' })).toBeVisible()
    // the old suggested questions are gone
    expect(screen.queryByRole('button', { name: 'What did I apply to this week?' })).toBeNull()
  })

  it('FR029_status_form_updates_a_job_and_closes', async () => {
    const user = userEvent.setup()
    show()

    await user.click(await screen.findByRole('button', { name: "Update a job's status" }))
    const form = screen.getByRole('form', { name: "Update a job's status" })
    expect(within(form).getByRole('button', { name: 'Update' })).toBeDisabled() // no job yet
    await user.selectOptions(await within(form).findByLabelText('Job'), 'job:j2')
    await user.selectOptions(within(form).getByLabelText('Status'), 'applied')
    await user.click(within(form).getByRole('button', { name: 'Update' }))

    await waitFor(() => expect(quick).toHaveLength(1))
    expect(quick[0]?.url).toMatch(/\/assistant\/conversations\/c1\/quick\/status$/)
    expect(quick[0]?.body).toEqual({ job: 'job:j2', status: 'applied' })
    await waitFor(() =>
      expect(screen.queryByRole('form', { name: "Update a job's status" })).not.toBeInTheDocument(),
    )
    expect(localStorage.getItem(CONVERSATION_KEY)).toBe('c1')
  })

  it('002m_flow_a_card_first_then_paste_then_choose_then_save', async () => {
    const user = userEvent.setup()
    show()

    await user.click(await screen.findByRole('button', { name: 'Email' }))
    expect(await screen.findByLabelText('Job post or link')).toBeInTheDocument()
    expect(staged[0]).toEqual({ name: 'begin', body: { kind: 'email' } })

    await user.click(screen.getByLabelText('Job post or link'))
    await user.paste('Platform Engineer at Initech. We build payment services in Python.')
    await user.click(screen.getByRole('button', { name: 'Continue' }))
    expect(await screen.findByRole('button', { name: 'LinkedIn message' })).toBeInTheDocument()
    expect(staged[1]?.name).toBe('post')

    await user.click(screen.getByRole('button', { name: 'LinkedIn message' }))
    expect(await screen.findByText(/Would you like me to save/)).toBeInTheDocument()
    expect(staged[2]).toEqual({ name: 'choose', body: { kind: 'referral_message' } })
    // the draft shows with its text, and the choice says what No does
    expect(await screen.findByText('Hi there, I would love to talk.')).toBeInTheDocument()
    expect(screen.getByText(/both discarded, so copy the draft first/)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Yes, save it' }))
    await waitFor(() => expect(staged.at(-1)?.name).toBe('save'))
    await waitFor(() => expect(screen.queryByText(/Would you like me to save/)).toBeNull())
    expect(screen.getByRole('button', { name: 'Email' })).toBeVisible() // the cards are back
  })

  it('002m_a_conversation_that_no_longer_exists_is_replaced_not_reported', async () => {
    localStorage.setItem(CONVERSATION_KEY, 'gone') // remembered by the browser, deleted since
    const user = userEvent.setup()
    show()

    await user.click(await screen.findByRole('button', { name: 'Email' }))

    await waitFor(() => expect(staged[0]?.name).toBe('begin'))
    expect(stagedUrls[0]).toContain('/conversations/c1/') // a fresh conversation, not 'gone'
    expect(localStorage.getItem(CONVERSATION_KEY)).toBe('c1')
    expect(screen.queryByText(/does not exist/)).not.toBeInTheDocument()
  })

  it('002m_flow_the_prompt_is_said_once_in_the_history_not_again_above_the_box', async () => {
    stored = [
      {
        id: 'm1',
        seq: 1,
        author: 'mikasa',
        text: 'Paste the job post, or a link to it, and I will write it.',
        status: 'complete',
        refs: [],
        signals: [],
        error: null,
        created_at: '',
        cards: [],
        changes: [],
      },
    ]
    stagedNow = {
      step: 'need_post',
      kind: 'email',
      label: null,
      job_ref: null,
      draft_ref: null,
      already_saved: false,
    }
    localStorage.setItem(CONVERSATION_KEY, 'c1')
    show()

    expect(await screen.findByLabelText('Job post or link')).toBeInTheDocument()
    expect(screen.getAllByText(/Paste the job post, or a link to it/)).toHaveLength(1)
  })

  it('002m_flow_enter_continues_and_shift_enter_makes_a_new_line', async () => {
    stagedNow = {
      step: 'need_post',
      kind: 'email',
      label: null,
      job_ref: null,
      draft_ref: null,
      already_saved: false,
    }
    localStorage.setItem(CONVERSATION_KEY, 'c1')
    const user = userEvent.setup()
    show()
    const box = await screen.findByLabelText('Job post or link')

    await user.type(
      box,
      'Platform Engineer at Initech, in Python and SQL, building payment services',
    )
    await user.keyboard('{Shift>}{Enter}{/Shift}')
    await user.type(box, 'Second line')

    expect(box).toHaveValue(
      'Platform Engineer at Initech, in Python and SQL, building payment services\nSecond line',
    )
    expect(staged.filter((call) => call.name === 'post')).toHaveLength(0)

    await user.keyboard('{Enter}')

    await waitFor(() => expect(staged.at(-1)?.name).toBe('post'))
    expect(staged.at(-1)?.body).toEqual({
      text: 'Platform Engineer at Initech, in Python and SQL, building payment services\nSecond line',
    })
  })

  it('002m_flow_no_discards', async () => {
    stagedNow = {
      step: 'ask_save',
      kind: 'email',
      label: 'Platform Engineer at Initech',
      job_ref: 'job:j9',
      draft_ref: 'draft:d1',
      already_saved: false,
    }
    localStorage.setItem(CONVERSATION_KEY, 'c1')
    const user = userEvent.setup()
    show()

    await user.click(await screen.findByRole('button', { name: 'No, discard' }))

    await waitFor(() => expect(staged.at(-1)?.name).toBe('discard'))
  })

  it('002m_flow_a_post_without_a_title_asks_for_title_and_company', async () => {
    stagedNow = {
      step: 'need_details',
      kind: null,
      label: 'Job post at jobs.example.com',
      job_ref: 'job:j9',
      draft_ref: null,
      already_saved: false,
    }
    localStorage.setItem(CONVERSATION_KEY, 'c1')
    const user = userEvent.setup()
    show()

    expect(await screen.findByLabelText('Job title')).toBeVisible()
    const next = screen.getByRole('button', { name: 'Continue' })
    expect(next).toBeDisabled()
    await user.type(screen.getByLabelText('Job title'), 'Platform Engineer')
    await user.type(screen.getByLabelText('Company'), 'Initech')
    await user.click(next)

    await waitFor(() =>
      expect(staged.at(-1)).toEqual({
        name: 'details',
        body: { title: 'Platform Engineer', company: 'Initech' },
      }),
    )
  })

  it('002m_flow_a_refusal_is_shown_and_the_step_stays', async () => {
    stagedRefusal = 'That is too short to be a job post. Paste the post or a link.'
    stagedNow = {
      step: 'need_post',
      kind: 'email',
      label: null,
      job_ref: null,
      draft_ref: null,
      already_saved: false,
    }
    localStorage.setItem(CONVERSATION_KEY, 'c1')
    const user = userEvent.setup()
    show()

    await user.click(await screen.findByLabelText('Job post or link'))
    await user.paste('hi')
    await user.click(screen.getByRole('button', { name: 'Continue' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('too short to be a job post')
    expect(screen.getByLabelText('Job post or link')).toHaveValue('hi')
  })

  it('002m_flow_a_link_typed_in_the_box_starts_the_flow_and_never_reaches_the_ai', async () => {
    let turned = false
    turn = () => {
      turned = true
      return sse([])
    }
    const user = userEvent.setup()
    show()
    await openTextBox(user)

    await user.type(
      screen.getByLabelText('Message to Mikasa'),
      'https://jobs.example.com/x/1{Enter}',
    )

    await waitFor(() => expect(staged[0]?.name).toBe('post'))
    expect(staged[0]?.body).toEqual({ text: 'https://jobs.example.com/x/1' })
    expect(turned).toBe(false)
  })

  it('002m_flow_a_pasted_posting_in_the_box_is_held_not_sent', async () => {
    turn = () =>
      json(
        { detail: 'That looks like a job posting.', status: 422, reason: 'looks_like_posting' },
        422,
      )
    const user = userEvent.setup()
    show()
    await openTextBox(user)

    await user.click(screen.getByLabelText('Message to Mikasa'))
    await user.paste('A long job posting that the server recognises.')
    await user.keyboard('{Enter}')

    await waitFor(() => expect(staged[0]?.name).toBe('post'))
    expect(screen.queryByText(/looks like a job posting/)).not.toBeInTheDocument()
  })

  it('FR029_quick_actions_work_without_an_ai_key', async () => {
    status = { available: false, reason: 'key_missing', provider_message: null }
    show()

    // status and add-a-job make no AI call; a draft says why when it cannot start
    expect(await screen.findByRole('button', { name: "Update a job's status" })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Add a job' })).toBeEnabled()
  })

  it('FR030_refusal_shows_chips', async () => {
    stored = [
      {
        id: 'm1',
        seq: 1,
        author: 'person',
        text: 'Write me a poem',
        status: 'complete',
        refs: [],
        signals: [],
        error: null,
        created_at: '',
        cards: [],
        changes: [],
      },
      {
        id: 'm2',
        seq: 2,
        author: 'mikasa',
        text: 'I can only help with your own job search in HireTitan. Try one of the quick actions.',
        status: 'complete',
        refs: [],
        signals: [],
        error: null,
        created_at: '',
        cards: [],
        changes: [],
      },
    ]
    localStorage.setItem(CONVERSATION_KEY, 'c1')
    show()

    expect(await screen.findByText(/I can only help with your own job search/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'LinkedIn connection message' })).toBeVisible()
  })

  it('002m_loading_dots_while_waiting_then_streaming_with_a_caret', async () => {
    let release = () => {}
    const hold = new Promise<void>((resolve) => (release = resolve))
    turn = () =>
      sse(
        [
          'event: text\ndata: {"delta": "You applied to "}\n\n',
          'event: text\ndata: {"delta": "two jobs."}\n\n',
        ],
        hold,
      )
    const user = userEvent.setup()
    const { container } = show()
    await screen.findByText(/Ask me about your jobs/)
    await openTextBox(user)

    await user.type(screen.getByLabelText('Message to Mikasa'), 'My jobs?{Enter}')

    // text arrived, so the dots are gone and a caret shows that more may come
    const reply = await screen.findByTestId('live-reply')
    await waitFor(() => expect(reply).toHaveTextContent('You applied to two jobs.'))
    expect(screen.queryByRole('status', { name: 'Mikasa is typing' })).not.toBeInTheDocument()
    expect(container.querySelector('.mikasa-caret')).not.toBeNull()
    release()
    await waitFor(() => expect(screen.queryByTestId('live-reply')).not.toBeInTheDocument())
  })

  it('002m_typing_dots_show_before_the_first_words', async () => {
    let release = () => {}
    const hold = new Promise<void>((resolve) => (release = resolve))
    turn = () => sse([], hold)
    const user = userEvent.setup()
    show()
    await screen.findByText(/Ask me about your jobs/)
    await openTextBox(user)

    await user.type(screen.getByLabelText('Message to Mikasa'), 'My jobs?{Enter}')

    expect(await screen.findByRole('status', { name: 'Mikasa is typing' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Stop' })).toBeInTheDocument()
    release()
    await waitFor(() =>
      expect(screen.queryByRole('status', { name: 'Mikasa is typing' })).not.toBeInTheDocument(),
    )
  })

  it('002m_the_form_button_spins_while_a_quick_action_runs', async () => {
    let release = () => {}
    const gate = new Promise<void>((resolve) => (release = resolve))
    const base = globalThis.fetch
    vi.stubGlobal('fetch', async (url: string, init?: RequestInit) => {
      if (String(url).includes('/quick/status')) await gate
      return base(url, init)
    })
    const user = userEvent.setup()
    show()

    await user.click(await screen.findByRole('button', { name: "Update a job's status" }))
    const form = screen.getByRole('form', { name: "Update a job's status" })
    await user.selectOptions(await within(form).findByLabelText('Job'), 'job:j2')
    await user.click(within(form).getByRole('button', { name: 'Update' }))

    expect(within(form).getByRole('button', { name: 'Update' })).toBeDisabled()
    expect(form.querySelector('.animate-spin')).not.toBeNull()
    release()
    await waitFor(() =>
      expect(screen.queryByRole('form', { name: "Update a job's status" })).toBeNull(),
    )
  })
})
