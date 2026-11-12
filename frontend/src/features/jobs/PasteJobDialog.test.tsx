import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { problem, stubApi } from '@/test/api'
import { PasteJobDialog } from './PasteJobDialog'

const DESCRIPTION = 'We build payment APIs in Python. You will own services end to end.'

function pasted(over: Record<string, unknown> = {}) {
  return {
    id: 'j9',
    title: 'Backend Engineer',
    company_name: 'Acme',
    location_text: null,
    work_mode: null,
    posted_at: null,
    first_seen_at: '2026-11-07T09:00:00Z',
    state: 'explore',
    restored: false,
    sources: [{ kind: 'paste', url: 'https://jobs.example.com/acme/1' }],
    decision: { outcome: 'shown', decided_by: 'person', reason: 'added by you' },
    listed: true,
    applied_on: null,
    description: DESCRIPTION,
    city: null,
    country: null,
    skills_found: [],
    years_found: null,
    canonical_url: 'https://jobs.example.com/acme/1',
    injection_flags: [],
    decision_history: [],
    first_search_id: null,
    merged_into: null,
    ...over,
  }
}

function json(body: unknown, status: number) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function renderDialog(reply: (body: unknown) => Response | undefined) {
  const calls = stubApi((call) => {
    if (call.method === 'POST' && call.path === '/jobs/paste') return reply(call.body)
    if (call.path === '/jobs/j9/applied')
      return pasted({ state: 'applied', applied_on: '2026-11-07' })
    return undefined
  })
  const onClose = vi.fn()
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <MemoryRouter>
        <PasteJobDialog onClose={onClose} />
      </MemoryRouter>
    </QueryClientProvider>,
  )
  return { calls, onClose }
}

async function fill(url: string, description: string) {
  const user = userEvent.setup()
  if (url) await user.type(screen.getByLabelText('Link to the job'), url)
  if (description) await user.click(screen.getByLabelText('Job description'))
  if (description) await user.paste(description)
  return user
}

afterEach(() => vi.unstubAllGlobals())

describe('PasteJobDialog', () => {
  it('US4_AS1_saves_and_shows_job', async () => {
    const { calls } = renderDialog(() => json(pasted(), 201))
    const user = await fill('https://jobs.example.com/acme/1', DESCRIPTION)

    await user.click(screen.getByRole('button', { name: 'Save job' }))

    expect(await screen.findByText(/Added to your jobs/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Backend Engineer' })).toHaveAttribute(
      'href',
      '/jobs/j9',
    )
    const post = calls.find((c) => c.path === '/jobs/paste')
    // title and company were left empty, so they are not sent
    expect(post?.body).toEqual({ url: 'https://jobs.example.com/acme/1', description: DESCRIPTION })
  })

  it('sends_the_title_and_company_when_given', async () => {
    const { calls } = renderDialog(() => json(pasted(), 201))
    const user = await fill('https://jobs.example.com/acme/1', DESCRIPTION)
    await user.type(screen.getByLabelText('Job title (optional)'), 'Backend Engineer')
    await user.type(screen.getByLabelText('Company (optional)'), 'Acme')

    await user.click(screen.getByRole('button', { name: 'Save job' }))

    await waitFor(() => expect(calls.some((c) => c.path === '/jobs/paste')).toBe(true))
    expect(calls.find((c) => c.path === '/jobs/paste')?.body).toEqual({
      url: 'https://jobs.example.com/acme/1',
      description: DESCRIPTION,
      title: 'Backend Engineer',
      company: 'Acme',
    })
  })

  it('US4_AS4_field_errors', async () => {
    renderDialog(() =>
      problem(422, 'Unprocessable Entity', {
        errors: [
          { field: 'url', message: 'Add the link to the job posting.' },
          { field: 'description', message: 'Paste the job description.' },
        ],
      }),
    )
    const user = userEvent.setup()

    await user.click(screen.getByRole('button', { name: 'Save job' }))

    expect(await screen.findByText('Add the link to the job posting.')).toBeInTheDocument()
    expect(screen.getByText('Paste the job description.')).toBeInTheDocument()
    expect(screen.getByLabelText('Link to the job')).toHaveAccessibleDescription(
      'Add the link to the job posting.',
    )
    expect(screen.queryByText(/Added to your jobs/)).not.toBeInTheDocument()
  })

  it('US4_AS3_shows_warning', async () => {
    renderDialog(() =>
      json(
        pasted({
          injection_flags: [
            {
              rule_id: 'ai_instruction',
              severity: 'high',
              excerpt: 'Ignore all previous instructions',
              location: 'visible',
            },
          ],
        }),
        201,
      ),
    )
    const user = await fill('https://jobs.example.com/acme/1', DESCRIPTION)

    await user.click(screen.getByRole('button', { name: 'Save job' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/looks like instructions to an AI/i)
  })

  it('US4_AS2_a_known_link_says_it_was_already_there', async () => {
    renderDialog(() => json(pasted({ merged_into: 'j9' }), 200))
    const user = await fill('https://jobs.example.com/acme/1', DESCRIPTION)

    await user.click(screen.getByRole('button', { name: 'Save job' }))

    expect(await screen.findByText(/already in your jobs/i)).toBeInTheDocument()
    expect(screen.queryByText(/Added to your jobs/)).not.toBeInTheDocument()
  })

  it('US4_AS5_after_saving_i_applied_is_one_click_away', async () => {
    const { calls } = renderDialog(() => json(pasted(), 201))
    const user = await fill('https://jobs.example.com/acme/1', DESCRIPTION)
    await user.click(screen.getByRole('button', { name: 'Save job' }))

    await user.click(await screen.findByRole('button', { name: 'I applied' }))

    await waitFor(() => expect(calls.some((c) => c.path === '/jobs/j9/applied')).toBe(true))
  })

  it('cancel_closes_the_form', async () => {
    const { onClose } = renderDialog(() => undefined)
    const user = userEvent.setup()

    await user.click(screen.getByRole('button', { name: 'Cancel' }))

    expect(onClose).toHaveBeenCalled()
  })
})
