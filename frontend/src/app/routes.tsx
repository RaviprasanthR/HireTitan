import { Navigate, type RouteObject } from 'react-router'
import {
  CompaniesPage,
  ExplorePage,
  JobDetailPage,
  NotFoundPage,
  PipelinePage,
  PreferencesPage,
  ProfileEditor,
  ProfilePage,
  ProfileReviewPage,
  ProfileVersionPage,
  ProfileVersionsPage,
  ReviewPage,
  RunSummaryPage,
  SearchHistoryPage,
  SearchRulesPage,
  SettingsPage,
} from './pages'
import { ProfileTabsLayout } from '@/features/profile/ProfileTabs'
import { SetupGate } from '@/features/setup/SetupGate'
import { Shell } from './Shell'

export const routes: RouteObject[] = [
  {
    element: <SetupGate />,
    children: [
      {
        element: <Shell />,
        children: [
          { path: '/', element: <ExplorePage /> },
          { path: '/pipeline', element: <PipelinePage /> },
          { path: '/applied', element: <Navigate to="/pipeline" replace /> },
          {
            element: <ProfileTabsLayout />,
            children: [
              { path: '/profile', element: <ProfilePage /> },
              { path: '/profile/preferences', element: <PreferencesPage /> },
              { path: '/profile/search-rules', element: <SearchRulesPage /> },
            ],
          },
          { path: '/preferences', element: <Navigate to="/profile/preferences" replace /> },
          { path: '/search/rules', element: <Navigate to="/profile/search-rules" replace /> },
          { path: '/profile/edit', element: <ProfileEditor /> },
          { path: '/profile/review/:reviewId', element: <ProfileReviewPage /> },
          { path: '/profile/versions', element: <ProfileVersionsPage /> },
          {
            path: '/profile/versions/:versionId',
            element: <ProfileVersionPage />,
          },
          { path: '/companies', element: <CompaniesPage /> },
          { path: '/search/history', element: <SearchHistoryPage /> },
          { path: '/search/runs/:id', element: <RunSummaryPage /> },
          { path: '/jobs/:id', element: <JobDetailPage /> },
          { path: '/review', element: <ReviewPage /> },
          { path: '/settings', element: <SettingsPage /> },
          { path: '*', element: <NotFoundPage /> },
        ],
      },
    ],
  },
]
