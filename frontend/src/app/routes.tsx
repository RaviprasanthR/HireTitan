import type { RouteObject } from 'react-router'
import {
  HomePage,
  NotFoundPage,
  PreferencesPage,
  ProfileEditor,
  ProfilePage,
  ProfileReviewPage,
  ProfileVersionPage,
  ProfileVersionsPage,
  ReviewPage,
  SettingsPage,
} from './pages'
import { Shell } from './Shell'

export const routes: RouteObject[] = [
  {
    element: <Shell />,
    children: [
      { path: '/', element: <HomePage /> },
      { path: '/profile', element: <ProfilePage /> },
      { path: '/profile/edit', element: <ProfileEditor /> },
      { path: '/profile/review/:reviewId', element: <ProfileReviewPage /> },
      { path: '/profile/versions', element: <ProfileVersionsPage /> },
      { path: '/profile/versions/:versionId', element: <ProfileVersionPage /> },
      { path: '/preferences', element: <PreferencesPage /> },
      { path: '/review', element: <ReviewPage /> },
      { path: '/settings', element: <SettingsPage /> },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
]
