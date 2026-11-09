import type { ReactNode } from 'react'
import { useParams } from 'react-router'
import { CompaniesPage } from '@/features/companies/CompaniesPage'
import { ExplorePage } from '@/features/explore/ExplorePage'
import { RunSummaryPage } from '@/features/explore/RunSummaryPage'
import { SearchHistoryPage } from '@/features/explore/SearchHistoryPage'
import { AppliedPage } from '@/features/jobs/AppliedPage'
import { JobDetailPage } from '@/features/jobs/JobDetailPage'
import { PreferencesPage } from '@/features/preferences/PreferencesPage'
import { ReviewPage } from '@/features/review/ReviewPage'
import { SearchRulesPage } from '@/features/search-rules/SearchRulesPage'
import { SettingsPage } from '@/features/settings/SettingsPage'
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

// Placeholder pages until a feature replaces them.
export function ProfileReviewPage() {
  const { reviewId } = useParams()
  return reviewId ? <ReviewEditor reviewId={reviewId} /> : <Page title="Review your profile" />
}
export const NotFoundPage = () => <Page title="Page not found" />

export {
  AppliedPage,
  CompaniesPage,
  ExplorePage,
  JobDetailPage,
  RunSummaryPage,
  SearchHistoryPage,
  SearchRulesPage,
  PreferencesPage,
  ReviewPage,
  SettingsPage,
  ProfileEditor,
  ProfilePage,
  VersionView as ProfileVersionPage,
  VersionsList as ProfileVersionsPage,
}
