import type { Onboarding } from './useOnboarding'

/** The card for the current setup step (steps 1 to 4 arrive in T075 and T076). */
export function StepCard({ onboarding }: { onboarding: Onboarding }) {
  return <p>Step {String(onboarding.step)}</p>
}
