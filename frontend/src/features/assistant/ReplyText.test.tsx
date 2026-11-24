import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ReplyText } from './ReplyText'

const JOB = 'job:0190a1b2-0000-7000-8000-000000000001'

function show(text: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <ReplyText text={text} />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('ReplyText', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('FR003_ref_links_open_items', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(
        async () =>
          new Response(
            JSON.stringify({
              ref: JOB,
              kind: 'job',
              title: 'Backend Engineer',
              subtitle: 'Acme',
              lines: ['Applied 22 Nov 2026'],
              link: '/jobs/0190a1b2-0000-7000-8000-000000000001',
            }),
            { headers: { 'Content-Type': 'application/json' } },
          ),
      ),
    )

    show(`You applied to [[${JOB}]]. See [[page:/settings/gmail]].`)

    const card = await screen.findByTestId('ref-card')
    expect(card).toHaveTextContent('Backend Engineer')
    expect(card).toHaveTextContent('Acme')
    expect(card).toHaveAttribute('href', '/jobs/0190a1b2-0000-7000-8000-000000000001')
    expect(screen.getByRole('link', { name: 'Settings → Gmail' })).toHaveAttribute(
      'href',
      '/settings/gmail',
    )
    expect(screen.queryByText(JOB, { exact: false })).not.toBeInTheDocument()
  })

  it('EC13_text_rendered_plain', () => {
    const { container } = show('<script>alert(1)</script> **bold** <b>x</b>')
    expect(container.querySelector('script')).toBeNull()
    expect(container.querySelector('b')).toBeNull()
    expect(container).toHaveTextContent('<script>alert(1)</script> **bold** <b>x</b>')
  })

  it('FR003_gone_item_says_so', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(
        async () =>
          new Response(JSON.stringify({ detail: 'gone' }), {
            status: 404,
            headers: { 'Content-Type': 'application/json' },
          }),
      ),
    )
    show(`[[${JOB}]]`)
    expect(await screen.findByText('This item no longer exists.')).toBeInTheDocument()
  })
})
