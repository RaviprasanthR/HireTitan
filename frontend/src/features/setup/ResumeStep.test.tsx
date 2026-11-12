import { useState } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { StepCard } from './StepCard'
import { type Onboarding, useOnboarding } from './useOnboarding'

const json = (body: unknown, status = 200, type = 'application/json') =>
  new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': type },
  })

let calls: { method: string; url: string; body?: unknown }[]
let aiStatus: string
let manualReply: () => Response

function onboarding(over: Partial<Onboarding> = {}): Onboarding {
  return {
    step: 2,
    display_name: 'Jane',
    open_review_id: null,
    active_run_id: null,
    ...over,
  }
}

beforeEach(() => {
  calls = []
  aiStatus = 'working'
  manualReply = () => json({ run_id: 'm1' }, 202)
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? 'GET'
      calls.push({ method, url, body: init?.body })
      if (url.endsWith('/status')) {
        return json({
          ai: {
            provider: 'openai',
            status: aiStatus,
            message: null,
            checked_at: null,
          },
          checklist: {
            key_ok: false,
            resume_uploaded: false,
            profile_confirmed: false,
            preferences_saved: false,
          },
        })
      }
      if (url.includes('/profile/reviews/manual')) return manualReply()
      if (url.endsWith('/resumes') && method === 'POST') {
        return json({ resume_file_id: 'f1', run_id: 'r1' }, 202)
      }
      if (url.includes('/runs/')) {
        return json({
          id: 'r1',
          workflow: 'profile_ingest',
          status: 'running',
          pause_reason: null,
          waiting_for: null,
          current_step: 'parsing',
          error: null,
          updated_at: '2026-11-04T10:00:00Z',
        })
      }
      if (url.endsWith('/onboarding') && method === 'GET') return json(onboarding())
      return json([])
    }),
  )
})
afterEach(() => vi.unstubAllGlobals())

/** The gate watches the step in the real app; the probe stands in for it. */
function GateProbe() {
  useOnboarding()
  return null
}

/** Holds the "going back to the name" state the setup gate owns in the real app. */
function CardWithState({ data }: { data: Onboarding }) {
  const [renaming, setRenaming] = useState(false)
  return <StepCard onboarding={data} renaming={renaming} setRenaming={setRenaming} />
}

function renderCard(data: Onboarding) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <GateProbe />
        <CardWithState data={data} />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

const manualCalls = () => calls.filter((c) => c.url.includes('/profile/reviews/manual'))

describe('ResumeStep', () => {
  it('US5_AS2_name_then_resume_step greets by name', async () => {
    renderCard(onboarding())
    expect(
      await screen.findByRole('heading', { name: 'Hi Jane, add your resume' }),
    ).toBeInTheDocument()
    expect(screen.getByLabelText('Resume file')).toBeInTheDocument()
  })

  it('US5_AS4_progress_then_moves_to_review', async () => {
    const user = userEvent.setup()
    renderCard(onboarding())
    const input = await screen.findByLabelText('Resume file')
    await user.upload(input, new File(['%PDF-1.4'], 'resume.pdf', { type: 'application/pdf' }))

    expect(await screen.findByText('Reading your resume…')).toBeInTheDocument()
    // the step is re-read so the card can move on when the review is ready
    const reads = () => calls.filter((c) => c.url.endsWith('/onboarding') && c.method === 'GET')
    await waitFor(() => expect(reads().length).toBeGreaterThan(1)) // read again after the upload
  })

  it('restores the progress of a resume that is already being read', async () => {
    renderCard(onboarding({ active_run_id: 'r1' }))
    expect(await screen.findByText('Reading your resume…')).toBeInTheDocument()
  })

  it('US5_AS5_missing_key_offers_type_it_in', async () => {
    aiStatus = 'missing'
    renderCard(onboarding())
    expect(await screen.findByText(/needs a working AI key/)).toHaveTextContent('OPENAI_API_KEY')
    expect(screen.getByRole('button', { name: 'Type it in myself' })).toBeEnabled()
  })

  it('US5_AS6_type_it_in_opens_a_manual_review', async () => {
    const user = userEvent.setup()
    renderCard(onboarding())
    await user.click(await screen.findByRole('button', { name: 'Type it in myself' }))

    await waitFor(() => expect(manualCalls()).toHaveLength(1))
    expect(manualCalls()[0]?.method).toBe('POST')
    expect(manualCalls()[0]?.url).not.toContain('cancel_active_run')
  })

  it('FR041_type_it_in_stops_active_run_after_confirm', async () => {
    const user = userEvent.setup()
    renderCard(onboarding({ active_run_id: 'r1' }))
    await user.click(await screen.findByRole('button', { name: 'Type it in myself' }))

    const dialog = await screen.findByRole('dialog')
    expect(dialog).toHaveTextContent('Stop reading the resume and type your profile in yourself?')
    expect(manualCalls()).toHaveLength(0) // nothing happens before the answer

    await user.click(within(dialog).getByRole('button', { name: 'Yes, stop and type it in' }))

    await waitFor(() => expect(manualCalls()).toHaveLength(1))
    expect(manualCalls()[0]?.url).toContain('cancel_active_run=true')
  })

  it('declining_the_stop_changes_nothing', async () => {
    const user = userEvent.setup()
    renderCard(onboarding({ active_run_id: 'r1' }))
    await user.click(await screen.findByRole('button', { name: 'Type it in myself' }))
    await user.click(
      within(await screen.findByRole('dialog')).getByRole('button', {
        name: 'Keep reading',
      }),
    )
    expect(manualCalls()).toHaveLength(0)
  })

  it('shows_why_type_it_in_failed', async () => {
    manualReply = () =>
      json(
        {
          title: 'Conflict',
          status: 409,
          detail: 'Your resume is being read right now. Try again in a moment.',
        },
        409,
        'application/problem+json',
      )
    const user = userEvent.setup()
    renderCard(onboarding())
    await user.click(await screen.findByRole('button', { name: 'Type it in myself' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('being read right now')
  })

  it('back_goes_to_the_name_and_keeps_it', async () => {
    const user = userEvent.setup()
    renderCard(onboarding())
    await user.click(await screen.findByRole('button', { name: 'Back' }))
    expect(await screen.findByLabelText('Your name')).toHaveValue('Jane')
  })
})

describe('NameStep', () => {
  it('US5_AS2_name_then_resume_step saves the name', async () => {
    const user = userEvent.setup()
    renderCard(onboarding({ step: 1, display_name: null }))
    expect(await screen.findByRole('heading', { name: 'Welcome to HireTitan' })).toBeInTheDocument()

    await user.type(screen.getByLabelText('Your name'), 'Jane Example')
    await user.click(screen.getByRole('button', { name: 'Continue' }))

    await waitFor(() => expect(calls.some((c) => c.method === 'PUT')).toBe(true))
    const put = calls.find((c) => c.method === 'PUT')
    expect(put?.url).toContain('/onboarding/name')
    expect(JSON.parse(String(put?.body))).toEqual({
      display_name: 'Jane Example',
    })
  })

  it('asks_for_a_name_before_continuing', async () => {
    const user = userEvent.setup()
    renderCard(onboarding({ step: 1, display_name: null }))
    await user.click(await screen.findByRole('button', { name: 'Continue' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Enter your name')
    expect(calls.some((c) => c.method === 'PUT')).toBe(false)
  })

  it('shows_a_server_error_on_the_name', async () => {
    const original = globalThis.fetch
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string, init?: RequestInit) =>
        (init?.method ?? 'GET') === 'PUT'
          ? json(
              {
                title: 'Some fields are not valid.',
                status: 422,
                errors: [
                  {
                    field: 'display_name',
                    message: 'The name must be 1 to 120 characters',
                  },
                ],
              },
              422,
              'application/problem+json',
            )
          : original(url, init),
      ),
    )
    const user = userEvent.setup()
    renderCard(onboarding({ step: 1, display_name: null }))
    await user.type(await screen.findByLabelText('Your name'), 'x')
    await user.click(screen.getByRole('button', { name: 'Continue' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('1 to 120 characters')
  })
})
