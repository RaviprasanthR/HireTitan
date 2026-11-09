import type { useStatus } from '@/api/useStatus'

type Step = {
  label: string
  done: boolean
  action: string
  to: string
  /** When set, the step cannot be started yet and this says why. */
  blocked?: string
}

export type Checklist = NonNullable<ReturnType<typeof useStatus>['data']>['checklist']

export function stepsFor(checklist: Checklist): Step[] {
  return [
    {
      label: 'AI key found and working',
      done: checklist.key_ok,
      action: 'Check the AI key',
      to: '/settings',
    },
    {
      label: 'Resume uploaded',
      done: checklist.resume_uploaded,
      action: 'Upload your resume',
      to: '/profile',
    },
    {
      label: 'Profile confirmed',
      done: checklist.profile_confirmed,
      action: 'Confirm your profile',
      to: '/profile',
    },
    {
      label: 'Preferences saved',
      done: checklist.preferences_saved,
      action: 'Set your preferences',
      to: '/preferences',
      blocked: checklist.profile_confirmed
        ? undefined
        : 'Available after you confirm your profile.',
    },
    {
      label: 'Search rules approved',
      done: checklist.rules_approved,
      action: 'Review your search rules',
      to: '/search/rules',
      blocked: checklist.preferences_saved
        ? undefined
        : 'Available after you save your preferences.',
    },
  ]
}

/** True when every step before the first search is done (FR-031). */
export function setupIsDone(checklist: Checklist | undefined): boolean {
  return checklist !== undefined && stepsFor(checklist).every((s) => s.done)
}
