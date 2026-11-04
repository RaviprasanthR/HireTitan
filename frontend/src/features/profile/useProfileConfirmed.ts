import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '@/api/client'
import type { components } from '@/api/schema'

type ProfileOut = components['schemas']['ProfileOut']

/** Whether a profile has been confirmed: `undefined` while we are still finding out. */
export function useProfileConfirmed(): boolean | undefined {
  const query = useQuery({
    queryKey: ['profile'],
    queryFn: () => apiFetch<ProfileOut>('/profile'),
    refetchOnWindowFocus: false,
  })
  if (query.isPending) return undefined
  return query.isSuccess && !!query.data.current
}
