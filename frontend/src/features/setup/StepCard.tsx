import { useState } from 'react'
import { NameStep } from './NameStep'
import { PreferencesStep } from './PreferencesStep'
import { ResumeStep } from './ResumeStep'
import { ReviewStep } from './ReviewStep'
import type { Onboarding } from './useOnboarding'

/** The card for the current setup step. `debounceMs` only shortens the autosave in tests. */
export function StepCard({
  onboarding,
  debounceMs,
}: {
  onboarding: Onboarding
  debounceMs?: number
}) {
  const [renaming, setRenaming] = useState(false)

  if (onboarding.step === 1 || renaming) {
    return (
      <NameStep initialName={onboarding.display_name ?? ''} onSaved={() => setRenaming(false)} />
    )
  }
  if (onboarding.step === 2) {
    return <ResumeStep onboarding={onboarding} onBack={() => setRenaming(true)} />
  }
  if (onboarding.step === 3) return <ReviewStep onboarding={onboarding} debounceMs={debounceMs} />
  return <PreferencesStep />
}
