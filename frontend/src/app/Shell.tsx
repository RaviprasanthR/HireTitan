import { Building2, House, Settings, User } from 'lucide-react'
import { Link, Outlet, useLocation } from 'react-router'
import { AiBanner } from './AiBanner'
import { UndoToast } from '@/features/jobs/UndoToast'
import { MikasaDock } from '@/features/assistant/MikasaDock'
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
      className="flex h-screen flex-col overflow-hidden bg-background text-foreground"
    >
      <header className="flex shrink-0 items-center justify-between gap-6 border-b border-white/[0.07] bg-[var(--ht-surface)]/80 px-6 py-2 backdrop-blur">
        <AppName />
        <nav aria-label="Main" className="flex items-center gap-1">
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
                  'ht-nav-link group relative flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium outline-none transition-colors duration-200',
                  'focus-visible:ring-2 focus-visible:ring-ring',
                  active ? 'text-foreground' : 'text-muted-foreground hover:text-foreground',
                )}
              >
                <Icon
                  aria-hidden
                  className={cn(
                    'size-4 transition-all duration-200',
                    active
                      ? 'text-[#a99ce6] drop-shadow-[0_0_6px_#a99ce6]'
                      : 'group-hover:-translate-y-px group-hover:text-[#a99ce6]',
                  )}
                />
                {label}
                {/* the highlight bar: full and glowing under the current section, grows in on hover */}
                <span
                  aria-hidden
                  className={cn(
                    'absolute inset-x-3 -bottom-2 h-0.5 origin-center rounded-full bg-gradient-to-r from-[#6f7fc4] via-[#a99ce6] to-[#e6e0ff] transition-transform duration-300',
                    active
                      ? 'scale-x-100 shadow-[0_0_10px_#a99ce6]'
                      : 'scale-x-0 group-hover:scale-x-60',
                  )}
                />
              </Link>
            )
          })}
        </nav>
      </header>
      <div data-testid="banner-slot">
        <AiBanner />
      </div>
      <main className="flex min-h-0 flex-1 flex-col overflow-y-auto">
        {/* a wide centred column; the chat floats over the page and may cover a little of it */}
        <div
          data-testid="page-column"
          className="mx-auto flex w-full max-w-[1800px] flex-1 flex-col px-4 py-6 md:px-6"
        >
          <Outlet />
        </div>
      </main>
      <MikasaDock />
      <UndoToast />
    </div>
  )
}
