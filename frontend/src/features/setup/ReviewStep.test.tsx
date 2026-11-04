import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { StepCard } from './StepCard'
import { type Onboarding, useOnboarding } from './useOnboarding'

const json = (body: unknown, status = 200, type = 'application/json') =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': type } })

const emptyProfile = {
  contact: { name: '', email: null, phone: null, location: null, links: [] },
  headline: null,
  summary: null,
  experience: [],
  education: [],
  skills: [],
  projects: [],
  certifications: [],
}

function review(over: Record<string, unknown> = {}) {
  return {
    id: 'rv1',
    run_id: 'r1',
    resume_file_id: null,
    status: 'open',
    extraction: emptyProfile,
    draft: null,
    draft_saved_at: null,
    dropped_items: [],
    flags: {
      hidden_text: [],
      injection_flags: [],
      truncated_at: null,
      extraction_outcome: 'manual',
    },
    compare_to: null,
    changed_paths: [],
    provenance: {
      prompt_name: 'extract_profile',
      prompt_version: '1',
      provider: 'none',
      model: 'none',
    },
    ...over,
  }
}

let calls: { method: string; url: string; body?: string }[]
let reply: Record<string, unknown>

beforeEach(() => {
  calls = []
  reply = review()
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? 'GET'
      calls.push({ method, url, body: init?.body as string | undefined })
      if (url.endsWith('/draft')) return json({ draft_saved_at: '2026-11-04T10:00:00Z' })
      if (url.endsWith('/discard')) return new Response(null, { status: 204 })
      if (url.endsWith('/confirm')) return json({ run_id: 'r1' }, 202)
      if (url.includes('/runs/'))
        return json({
          id: 'r1',
          status: 'done',
          workflow: 'profile_ingest',
          pause_reason: null,
          waiting_for: null,
          current_step: null,
          error: null,
          updated_at: '2026-11-04T10:00:00Z',
        })
      if (url.includes('/profile/reviews/')) return json(reply)
      if (url.endsWith('/onboarding'))
        return json({ step: 3, display_name: 'Jane', open_review_id: 'rv1', active_run_id: null })
      return json([])
    }),
  )
})
afterEach(() => vi.unstubAllGlobals())

function GateProbe() {
  useOnboarding()
  return null
}

function renderStep(over: Partial<Onboarding> = {}) {
  const data: Onboarding = {
    step: 3,
    display_name: 'Jane',
    open_review_id: 'rv1',
    active_run_id: null,
    ...over,
  }
  return render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <MemoryRouter>
        <GateProbe />
        <StepCard onboarding={data} debounceMs={10} />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('ReviewStep', () => {
  it('FR039_name_prefills_empty_review', async () => {
    renderStep()
    expect(await screen.findByLabelText('Name')).toHaveValue('Jane')
  })

  it('FR039_a_name_from_the_resume_is_kept', async () => {
    reply = review({
      extraction: { ...emptyProfile, contact: { ...emptyProfile.contact, name: 'Janet Resume' } },
    })
    renderStep()
    expect(await screen.findByLabelText('Name')).toHaveValue('Janet Resume')
  })

  it('FR039_a_saved_draft_wins_over_the_name', async () => {
    reply = review({
      draft: { ...emptyProfile, contact: { ...emptyProfile.contact, name: 'Typed Earlier' } },
      draft_saved_at: '2026-11-04T09:00:00Z',
    })
    renderStep()
    expect(await screen.findByLabelText('Name')).toHaveValue('Typed Earlier')
  })

  it('US5_AS6_manual_entry_autosaves_in_card', async () => {
    const user = userEvent.setup()
    renderStep()
    const skills = await screen.findByLabelText('Skills (one per line)')
    await user.type(skills, 'Python')

    await waitFor(() => expect(calls.some((c) => c.url.endsWith('/draft'))).toBe(true))
    expect(screen.getByText('Draft saved')).toBeInTheDocument()
    expect(screen.queryByText(/Extracted with/)).not.toBeInTheDocument() // typed in, not extracted
    expect(
      screen.queryByRole('heading', { level: 1, name: 'Review your profile' }),
    ).not.toBeInTheDocument()
  })

  it('confirming_stays_in_the_card_and_re_reads_the_step', async () => {
    const user = userEvent.setup()
    renderStep()
    await user.type(await screen.findByLabelText('Skills (one per line)'), 'Python')
    const reads = () => calls.filter((c) => c.url.endsWith('/onboarding')).length
    await waitFor(() => expect(reads()).toBeGreaterThan(0))
    const before = reads()

    await user.click(screen.getByRole('button', { name: 'Confirm profile' }))

    await waitFor(() => expect(calls.some((c) => c.url.endsWith('/confirm'))).toBe(true))
    await waitFor(() => expect(reads()).toBeGreaterThan(before))
  })

  it('FR041_back_to_upload_discards_after_confirm', async () => {
    const user = userEvent.setup()
    renderStep()
    await user.click(await screen.findByRole('button', { name: 'Back to upload' }))

    const dialog = await screen.findByRole('dialog')
    expect(dialog).toHaveTextContent('Discard this profile and upload a different resume?')
    expect(calls.some((c) => c.url.endsWith('/discard'))).toBe(false)

    await user.click(within(dialog).getByRole('button', { name: 'Yes, discard' }))

    await waitFor(() => expect(calls.some((c) => c.url.endsWith('/discard'))).toBe(true))
  })
})
