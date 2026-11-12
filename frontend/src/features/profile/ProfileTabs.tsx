import { NavLink, Outlet } from 'react-router'

const TABS = [
  { to: '/profile', label: 'Profile' },
  { to: '/profile/preferences', label: 'Preferences' },
  { to: '/profile/search-rules', label: 'Search rules' },
]

/** Profile, Preferences and Search rules: the three things that describe you to a search. */
export function ProfileTabs() {
  return (
    <nav aria-label="Profile tabs" className="flex gap-2 border-b border-divider">
      {TABS.map((tab) => (
        <NavLink
          key={tab.to}
          to={tab.to}
          end
          className={({ isActive }) =>
            `-mb-px border-b-2 px-3 py-2 text-sm font-medium ${
              isActive
                ? 'border-[#f0a35e] text-[#f0a35e]'
                : 'border-transparent text-muted-small hover:text-foreground'
            }`
          }
        >
          {tab.label}
        </NavLink>
      ))}
    </nav>
  )
}

/** Route layout: the tabs above whichever of the three pages is open. */
export function ProfileTabsLayout() {
  return (
    <div className="space-y-6">
      <ProfileTabs />
      <Outlet />
    </div>
  )
}
