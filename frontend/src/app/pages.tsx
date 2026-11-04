import type { ReactNode } from 'react'
import { useParams } from 'react-router'
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

// Placeholders: each feature replaces its page (Home, Preferences, Review, Settings).
export const HomePage = () => <Page title="Home" />
export function ProfileReviewPage() {
  const { reviewId } = useParams()
  return reviewId ? <ReviewEditor reviewId={reviewId} /> : <Page title="Review your profile" />
}
export const PreferencesPage = () => <Page title="Preferences" />
export const ReviewPage = () => <Page title="Review" />
export const SettingsPage = () => <Page title="Settings" />
export const NotFoundPage = () => <Page title="Page not found" />

export { ProfileEditor, ProfilePage, VersionView as ProfileVersionPage, VersionsList as ProfileVersionsPage }
