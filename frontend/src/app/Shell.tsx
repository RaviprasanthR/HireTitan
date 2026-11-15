import { Building2, House, Settings, User } from 'lucide-react'
import { Link, Outlet, useLocation } from 'react-router'
import { AiBanner } from './AiBanner'
import { UndoToast } from '@/features/jobs/UndoToast'
import { AppName } from '@/components/AppName'
import { cn } from '@/lib/utils'

const sections = [
  { to: '/', label: 'Home', end: true, Icon: House, also: ['/explore'] },
  { to: '/companies', label: 'Companies', end: false, Icon: Building2 },
  { to: '/profile', label: 'Profile', end: false, Icon: User },
  { to: '/settings', label: 'Settings', end: false, Icon: Settings },
] as const

export function Shell() {
  const { pathname } = useLocation()
  return (
    <div
      data-testid="app-root"
      className="flex h-screen overflow-hidden bg-background text-foreground"
    >
      <aside className="flex w-56 shrink-0 flex-col gap-6 border-r border-white/[0.07] bg-[var(--ht-surface)] p-4">
        <AppName className="px-3" />
        <nav aria-label="Main" className="flex flex-col gap-1">
          {sections.map(({ to, label, end, Icon, ...rest }) => {
            // Home also covers the Explore tab, which is not under "/" as far as a path goes
            const also: readonly string[] = 'also' in rest ? rest.also : []
            const active = end
              ? pathname === to || also.includes(pathname)
              : pathname === to || pathname.startsWith(`${to}/`)
            return (
              <Link
                key={to}
                to={to}
                aria-current={active ? 'page' : undefined}
                className={cn(
                  'flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium outline-none',
                  'focus-visible:ring-2 focus-visible:ring-ring',
                  active ? 'bg-primary text-primary-foreground' : 'hover:bg-divider',
                )}
              >
                <Icon aria-hidden className="size-4" />
                {label}
              </Link>
            )
          })}
        </nav>
      </aside>
      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        <div data-testid="banner-slot">
          <AiBanner />
        </div>
        <main className="flex min-h-0 flex-1 flex-col overflow-y-auto p-8">
          <Outlet />
        </main>
      </div>
      <UndoToast />
    </div>
  )
}
