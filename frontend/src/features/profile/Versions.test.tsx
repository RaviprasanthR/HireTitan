import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ProfileEditor } from './ProfileEditor'
import { VersionView } from './VersionView'
import { VersionsList } from './VersionsList'

const json = (body: unknown, status = 200, type = 'application/json') =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': type } })

function content(overrides: object = {}) {
  return {
    contact: { name: 'Jane Example', email: null, phone: null, location: 'Pune', links: [] },
    headline: 'Backend engineer',
    summary: null,
    experience: [
      {
        id: 'aaaaaaaa-0000-0000-0000-000000000001',
        employer: 'Acme Corp',
        title: 'Engineer',
        location: null,
        start: { year: 2021, month: 1 },
        end: null,
        current: true,
        bullets: ['Built things'],
      },
    ],
    education: [],
    skills: ['Python', 'Go'],
    projects: [],
    certifications: [],
    ...overrides,
  }
}

function version(overrides: object = {}) {
  return {
    id: 'bbbbbbbb-0000-0000-0000-000000000002',
    number: 2,
    created_at: '2026-11-04T10:00:00Z',
    created_by: 'manual_edit',
    source_file_name: null,
    source_deleted: false,
    is_current: true,
    ...overrides,
  }
}

type Handler = (init?: RequestInit) => Response | Promise<Response>
let routes: Record<string, Handler>
let calls: { url: string; method: string; body?: string }[]

beforeEach(() => {
  routes = {}
  calls = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? 'GET'
      calls.push({ url, method, body: init?.body as string | undefined })
      const handler = routes[`${method} ${url}`]
      return handler
        ? handler(init)
        : json(
            { title: 'Not found', status: 404, detail: `no route ${method} ${url}` },
            404,
            'application/problem+json',
          )
    }),
  )
})
afterEach(() => vi.unstubAllGlobals())

function renderAt(path: string, element: ReactNode, routePath = path) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path={routePath} element={element} />
          <Route path="/profile" element={<p>Profile home</p>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

function postBody(): Record<string, unknown> {
  const post = calls.find((c) => c.method === 'POST')
  if (!post?.body) throw new Error('no POST was made')
  return JSON.parse(post.body) as Record<string, unknown>
}

describe('Versions', () => {
  it('FR021_lists_versions_with_source_and_current', async () => {
    routes['GET /api/v1/profile/versions'] = () =>
      json([
        version({ id: 'v2', number: 2, created_by: 'manual_edit', is_current: true }),
        version({
          id: 'v1',
          number: 1,
          created_by: 'extraction',
          source_file_name: 'resume.pdf',
          is_current: false,
        }),
        version({
          id: 'v0',
          number: 0,
          created_by: 'extraction',
          source_deleted: true,
          is_current: false,
        }),
      ])
    renderAt('/profile/versions', <VersionsList />)

    const items = await screen.findAllByRole('listitem')
    const row = (i: number): HTMLElement => {
      const el = items[i]
      if (!el) throw new Error(`no list item ${i}`)
      return el
    }
    expect(within(row(0)).getByText('Version 2')).toBeInTheDocument()
    expect(within(row(0)).getByText('Current')).toBeInTheDocument()
    expect(within(row(0)).getByText(/edited by hand/i)).toBeInTheDocument()
    expect(within(row(1)).getByText(/resume\.pdf/)).toBeInTheDocument()
    expect(within(row(1)).queryByText('Current')).not.toBeInTheDocument()
    expect(within(row(2)).getByText(/source file was deleted/i)).toBeInTheDocument()
    expect(within(row(1)).getByRole('link', { name: /view/i })).toHaveAttribute(
      'href',
      '/profile/versions/v1',
    )
  })

  it('empty_state_points_to_upload_or_manual', async () => {
    routes['GET /api/v1/profile/versions'] = () => json([])
    renderAt('/profile/versions', <VersionsList />)
    expect(await screen.findByText(/no profile yet/i)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /fill in by hand/i })).toHaveAttribute(
      'href',
      '/profile/edit',
    )
  })

  it('a_version_is_shown_read_only', async () => {
    routes['GET /api/v1/profile/versions/v1'] = () =>
      json({
        ...version({ id: 'v1', number: 1, source_deleted: true, is_current: false }),
        content: content(),
      })
    renderAt('/profile/versions/v1', <VersionView />, '/profile/versions/:versionId')

    expect(await screen.findByRole('heading', { name: /version 1/i })).toBeInTheDocument()
    expect(screen.getByText('Jane Example')).toBeInTheDocument()
    expect(screen.getByText('Acme Corp')).toBeInTheDocument()
    expect(screen.getByText('Built things')).toBeInTheDocument()
    expect(screen.getByText('Python')).toBeInTheDocument()
    expect(screen.getByText(/source file was deleted/i)).toBeInTheDocument()
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
  })
})

describe('ProfileEditor', () => {
  it('FR019_manual_create_posts_version', async () => {
    routes['GET /api/v1/profile'] = () => json({ current: null })
    routes['POST /api/v1/profile/versions'] = () =>
      json(version({ number: 1, created_by: 'manual' }), 201)
    renderAt('/profile/edit', <ProfileEditor />)
    const user = userEvent.setup()

    await user.type(await screen.findByLabelText('Name'), 'Sam Sample')
    await user.type(screen.getByLabelText(/skills \(one per line\)/i), 'Python{Enter}SQL')
    await user.click(screen.getByRole('button', { name: /save profile/i }))

    await waitFor(() => expect(calls.some((c) => c.method === 'POST')).toBe(true))
    const body = postBody() as { contact: { name: string }; skills: string[] }
    expect(body.contact.name).toBe('Sam Sample')
    expect(body.skills).toEqual(['Python', 'SQL'])
    expect(await screen.findByText('Profile home')).toBeInTheDocument()
  })

  it('FR020_edit_creates_new_version', async () => {
    routes['GET /api/v1/profile'] = () =>
      json({ current: { ...version({ number: 1, created_by: 'manual' }), content: content() } })
    routes['POST /api/v1/profile/versions'] = () => json(version({ number: 2 }), 201)
    renderAt('/profile/edit', <ProfileEditor />)
    const user = userEvent.setup()

    const headline = await screen.findByLabelText('Headline')
    expect(headline).toHaveValue('Backend engineer') // prefilled from the current version
    await user.clear(headline)
    await user.type(headline, 'Staff engineer')
    await user.click(screen.getByRole('button', { name: /save profile/i }))

    await waitFor(() => expect(calls.some((c) => c.method === 'POST')).toBe(true))
    const body = postBody() as { headline: string; experience: { employer: string }[] }
    expect(body.headline).toBe('Staff engineer')
    expect(body.experience[0]?.employer).toBe('Acme Corp')
    expect(calls.some((c) => c.method === 'PUT')).toBe(false) // the old version is never changed
  })

  it('says_that_saving_makes_a_new_version_when_a_profile_exists', async () => {
    routes['GET /api/v1/profile'] = () =>
      json({ current: { ...version({ number: 1, created_by: 'manual' }), content: content() } })
    renderAt('/profile/edit', <ProfileEditor />)
    expect(await screen.findByText(/saves as a new version/i)).toBeInTheDocument()
  })

  it('rule_errors_from_the_server_appear_on_their_fields', async () => {
    routes['GET /api/v1/profile'] = () => json({ current: null })
    routes['POST /api/v1/profile/versions'] = () =>
      json(
        {
          title: 'Unprocessable',
          status: 422,
          detail: 'This profile cannot be saved yet.',
          errors: [
            { field: 'contact.name', message: 'Name is required' },
            { field: 'profile', message: 'Add at least one of experience, education or skills' },
          ],
        },
        422,
        'application/problem+json',
      )
    renderAt('/profile/edit', <ProfileEditor />)
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: /save profile/i }))

    expect(await screen.findByText('Name is required')).toBeInTheDocument()
    expect(screen.getByText(/add at least one of experience/i)).toBeInTheDocument()
    expect(screen.queryByText('Profile home')).not.toBeInTheDocument()
  })
})
