import type { ReactNode } from 'react'

function Page({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <section className="space-y-4">
      <h1 className="text-2xl font-semibold">{title}</h1>
      {children}
    </section>
  )
}

// Placeholders: each feature replaces its page (Home, Profile, Preferences, Review, Settings).
export const HomePage = () => <Page title="Home" />
export const ProfilePage = () => <Page title="Profile" />
export const ProfileReviewPage = () => <Page title="Review your profile" />
export const ProfileVersionPage = () => <Page title="Profile version" />
export const PreferencesPage = () => <Page title="Preferences" />
export const ReviewPage = () => <Page title="Review" />
export const SettingsPage = () => <Page title="Settings" />
export const NotFoundPage = () => <Page title="Page not found" />
