import { useState } from 'react'
import { NameStep } from './NameStep'
import { ResumeStep } from './ResumeStep'
import type { Onboarding } from './useOnboarding'

/** The card for the current setup step (steps 3 and 4 arrive in T076). */
export function StepCard({ onboarding }: { onboarding: Onboarding }) {
  const [renaming, setRenaming] = useState(false)

  if (onboarding.step === 1 || renaming) {
    return (
      <NameStep initialName={onboarding.display_name ?? ''} onSaved={() => setRenaming(false)} />
    )
  }
  if (onboarding.step === 2) {
    return <ResumeStep onboarding={onboarding} onBack={() => setRenaming(true)} />
  }
  return <p>Step {String(onboarding.step)}</p>
}
