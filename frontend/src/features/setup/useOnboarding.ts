import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '@/api/client'
import type { components } from '@/api/schema'

export type Onboarding = components['schemas']['OnboardingOut']
export type SetupStep = Onboarding['step']

/** Which setup card to show, from saved data; refetched on run and profile events. */
export function useOnboarding() {
  return useQuery({
    queryKey: ['onboarding'],
    queryFn: () => apiFetch<Onboarding>('/onboarding'),
    refetchOnWindowFocus: false,
  })
}
