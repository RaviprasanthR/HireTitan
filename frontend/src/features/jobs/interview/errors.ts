import { ApiError } from '@/api/client'

export function errorOf(error: unknown): ApiError | null {
  return error instanceof ApiError ? error : null
}
