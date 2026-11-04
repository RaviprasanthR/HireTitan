import type { RouteObject } from 'react-router'
import {
  HomePage,
  NotFoundPage,
  PreferencesPage,
  ProfilePage,
  ProfileReviewPage,
  ProfileVersionPage,
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
      { path: '/profile/review/:reviewId', element: <ProfileReviewPage /> },
      { path: '/profile/versions/:versionId', element: <ProfileVersionPage /> },
      { path: '/preferences', element: <PreferencesPage /> },
      { path: '/review', element: <ReviewPage /> },
      { path: '/settings', element: <SettingsPage /> },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
]
