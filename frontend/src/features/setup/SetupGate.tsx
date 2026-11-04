import { Outlet, useLocation } from 'react-router'
import { SettingsPage } from '@/features/settings/SettingsPage'
import { SetupLayout } from './SetupLayout'
import { StepCard } from './StepCard'
import { useOnboarding } from './useOnboarding'

/**
 * Wraps the whole app. While setup is not finished every page is replaced by the setup card
 * for the saved step; Settings stays reachable for the budget cap (FR-041). Once setup is
 * done the normal app shows (FR-040).
 */
export function SetupGate() {
  const query = useOnboarding()
  const { pathname } = useLocation()

  if (query.isPending) {
    return (
      <SetupLayout>
        <p>Loading…</p>
      </SetupLayout>
    )
  }
  if (query.isError || !query.data) {
    return (
      <SetupLayout>
        <p role="alert">Could not load your setup. Reload the page to try again.</p>
      </SetupLayout>
    )
  }
  const { step } = query.data
  if (step === 'done') return <Outlet />

  if (pathname === '/settings') {
    return (
      <SetupLayout closeTo="/">
        <SettingsPage />
      </SetupLayout>
    )
  }
  return (
    <SetupLayout step={step}>
      <StepCard onboarding={query.data} />
    </SetupLayout>
  )
}
