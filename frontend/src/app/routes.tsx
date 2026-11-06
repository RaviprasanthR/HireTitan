import type { RouteObject } from 'react-router'
import {
  AppliedPage,
  ExplorePage,
  JobDetailPage,
  NotFoundPage,
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
          { path: '/applied', element: <AppliedPage /> },
          { path: '/profile', element: <ProfilePage /> },
          { path: '/profile/edit', element: <ProfileEditor /> },
          { path: '/profile/review/:reviewId', element: <ProfileReviewPage /> },
          { path: '/profile/versions', element: <ProfileVersionsPage /> },
          {
            path: '/profile/versions/:versionId',
            element: <ProfileVersionPage />,
          },
          { path: '/preferences', element: <PreferencesPage /> },
          { path: '/search/rules', element: <SearchRulesPage /> },
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
