const API_PREFIX = '/api/v1'

export type FieldError = { field: string; message: string }

/** An RFC 9457 problem+json body; extra members (like `open_review_id`) are kept. */
export type Problem = {
  type?: string
  title?: string
  status?: number
  detail?: string
  errors?: FieldError[]
  [member: string]: unknown
}

export class ApiError extends Error {
  readonly status: number
  readonly title: string
  readonly detail: string
  readonly fieldErrors: FieldError[]
  readonly problem: Problem

  constructor(status: number, problem: Problem) {
    const title = problem.title ?? `Request failed (${status})`
    const detail = problem.detail ?? title
    super(detail)
    this.name = 'ApiError'
    this.status = status
    this.title = title
    this.detail = detail
    this.fieldErrors = problem.errors ?? []
    this.problem = problem
  }

  fieldError(field: string): string | undefined {
    return this.fieldErrors.find((e) => e.field === field)?.message
  }
}

export type ApiInit = Omit<RequestInit, 'body'> & { body?: BodyInit | null; json?: unknown }

async function readProblem(response: Response): Promise<Problem> {
  const type = response.headers.get('Content-Type') ?? ''
  if (type.includes('json')) {
    try {
      return (await response.json()) as Problem
    } catch {
      // fall through to the generic problem
    }
  }
  return { title: response.statusText || `Request failed (${response.status})` }
}

/** Typed `fetch` for the backend: JSON in and out, problem+json turned into `ApiError`. */
export async function apiFetch<T = undefined>(path: string, init: ApiInit = {}): Promise<T> {
  const { json, headers, body, ...rest } = init
  const merged = new Headers(headers)
  let payload: BodyInit | null | undefined = body
  if (json !== undefined) {
    payload = JSON.stringify(json)
    merged.set('Content-Type', 'application/json')
  }
  const response = await fetch(`${API_PREFIX}${path}`, { ...rest, headers: merged, body: payload })
  if (!response.ok) throw new ApiError(response.status, await readProblem(response))
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}
