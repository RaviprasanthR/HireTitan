import { Outlet, NavLink } from 'react-router'
import { cn } from '@/lib/utils'

const sections = [
  { to: '/', label: 'Home', end: true },
  { to: '/profile', label: 'Profile', end: false },
  { to: '/preferences', label: 'Preferences', end: false },
  { to: '/review', label: 'Review', end: false },
  { to: '/settings', label: 'Settings', end: false },
] as const

export function Shell() {
  return (
    <div data-testid="app-root" className="flex min-h-screen bg-background text-foreground">
      <aside className="flex w-56 shrink-0 flex-col gap-6 bg-surface p-4">
        <span className="px-3 text-lg font-semibold">HireTitan</span>
        <nav aria-label="Main" className="flex flex-col gap-1">
          {sections.map(({ to, label, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                cn(
                  'rounded-md px-3 py-2 text-sm font-medium outline-none',
                  'focus-visible:ring-2 focus-visible:ring-ring',
                  isActive ? 'bg-primary text-primary-foreground' : 'hover:bg-divider',
                )
              }
            >
              {label}
            </NavLink>
          ))}
        </nav>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        {/* Setup, key and budget banners render here. */}
        <div data-testid="banner-slot" />
        <main className="flex-1 p-8">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
