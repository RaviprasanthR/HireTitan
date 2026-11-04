import type { ReactNode } from 'react'
import { Navigate, useParams } from 'react-router'
import { PreferencesPage as PreferencesForm } from '@/features/preferences/PreferencesPage'
import { useProfileConfirmed } from '@/features/profile/useProfileConfirmed'
import { ProfileEditor } from '@/features/profile/ProfileEditor'
import { ProfilePage } from '@/features/profile/ProfilePage'
import { ReviewEditor } from '@/features/profile/ReviewEditor'
import { VersionView } from '@/features/profile/VersionView'
import { VersionsList } from '@/features/profile/VersionsList'

function Page({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <section className="space-y-4">
      <h1 className="text-2xl font-semibold">{title}</h1>
      {children}
    </section>
  )
}

// Placeholders: each feature replaces its page (Home, Review, Settings).
export const HomePage = () => <Page title="Home" />
export function ProfileReviewPage() {
  const { reviewId } = useParams()
  return reviewId ? <ReviewEditor reviewId={reviewId} /> : <Page title="Review your profile" />
}
/** Preferences are not shown, or even loaded, until a profile has been confirmed. */
export function PreferencesPage() {
  const confirmed = useProfileConfirmed()
  if (confirmed === undefined) return <p>Loading…</p>
  if (!confirmed) return <Navigate to="/profile" replace />
  return <PreferencesForm />
}
export const ReviewPage = () => <Page title="Review" />
export const SettingsPage = () => <Page title="Settings" />
export const NotFoundPage = () => <Page title="Page not found" />

export { ProfileEditor, ProfilePage, VersionView as ProfileVersionPage, VersionsList as ProfileVersionsPage }
