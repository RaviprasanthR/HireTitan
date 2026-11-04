import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, apiFetch } from './client'

function respond(status: number, body: unknown, contentType = 'application/problem+json') {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(
      new Response(body === undefined ? null : JSON.stringify(body), {
        status,
        headers: { 'Content-Type': contentType },
      }),
    ),
  )
}

afterEach(() => {
  vi.unstubAllGlobals()
})

function lastInit(): RequestInit {
  const init = vi.mocked(fetch).mock.calls[0]?.[1]
  if (!init) throw new Error('fetch was not called with an init')
  return init
}

describe('apiFetch', () => {
  it('maps_problem_json_field_errors', async () => {
    respond(422, {
      type: 'https://httpstatuses.io/422',
      title: 'Unprocessable Content',
      status: 422,
      detail: 'Some fields are not valid.',
      errors: [
        { field: 'contact.name', message: 'Name is required' },
        { field: 'experience.0.end', message: 'End is before start' },
      ],
    })
    const error = await apiFetch('/profile/reviews/1/confirm', { method: 'POST' }).catch(
      (e: unknown) => e,
    )
    expect(error).toBeInstanceOf(ApiError)
    const api = error as ApiError
    expect(api.status).toBe(422)
    expect(api.title).toBe('Unprocessable Content')
    expect(api.detail).toBe('Some fields are not valid.')
    expect(api.fieldErrors).toEqual([
      { field: 'contact.name', message: 'Name is required' },
      { field: 'experience.0.end', message: 'End is before start' },
    ])
    expect(api.fieldError('contact.name')).toBe('Name is required')
    expect(api.fieldError('nope')).toBeUndefined()
  })

  it('returns_parsed_json_on_success_under_the_api_prefix', async () => {
    respond(200, { status: 'ok' }, 'application/json')
    await expect(apiFetch<{ status: string }>('/health')).resolves.toEqual({ status: 'ok' })
    expect(fetch).toHaveBeenCalledWith('/api/v1/health', expect.anything())
  })

  it('returns_undefined_for_204', async () => {
    respond(204, undefined)
    await expect(apiFetch('/resumes/1', { method: 'DELETE' })).resolves.toBeUndefined()
  })

  it('sends_json_bodies_with_a_content_type', async () => {
    respond(200, {}, 'application/json')
    await apiFetch('/x', { method: 'PUT', json: { a: 1 } })
    const init = lastInit()
    expect(init.body).toBe('{"a":1}')
    expect(new Headers(init.headers).get('Content-Type')).toBe('application/json')
  })

  it('does_not_set_content_type_for_form_data', async () => {
    respond(202, {}, 'application/json')
    const body = new FormData()
    body.append('file', new Blob(['x']), 'a.pdf')
    await apiFetch('/resumes', { method: 'POST', body })
    const init = lastInit()
    expect(new Headers(init.headers).has('Content-Type')).toBe(false)
  })

  it('falls_back_to_a_generic_error_for_non_problem_responses', async () => {
    respond(502, '<html>bad gateway</html>', 'text/html')
    const error = (await apiFetch('/x').catch((e: unknown) => e)) as ApiError
    expect(error).toBeInstanceOf(ApiError)
    expect(error.status).toBe(502)
    expect(error.fieldErrors).toEqual([])
    expect(error.message).toBeTruthy()
  })

  it('keeps_extra_problem_members_like_open_review_id', async () => {
    respond(409, { title: 'Conflict', status: 409, detail: 'A review is open', open_review_id: 'r1' })
    const error = (await apiFetch('/resumes', { method: 'POST' }).catch((e: unknown) => e)) as ApiError
    expect(error.problem.open_review_id).toBe('r1')
  })
})
