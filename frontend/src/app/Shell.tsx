import { Briefcase, Building2, Settings, User } from 'lucide-react'
import { Link, Outlet, useLocation } from 'react-router'
import { AiBanner } from './AiBanner'
import { UndoToast } from '@/features/jobs/UndoToast'
import { MikasaDock } from '@/features/assistant/MikasaDock'
import { AppName } from '@/components/AppName'
import { cn } from '@/lib/utils'

const sections = [
  { to: '/', label: 'Jobs', end: true, Icon: Briefcase, also: ['/explore'] },
  { to: '/companies', label: 'Companies', end: false, Icon: Building2 },
  { to: '/profile', label: 'Profile', end: false, Icon: User },
  { to: '/settings', label: 'Settings', end: false, Icon: Settings },
] as const

export function Shell() {
  const { pathname } = useLocation()
  return (
    <div data-testid="app-root" className="flex h-dvh flex-col bg-background text-foreground">
      <header className="flex shrink-0 items-center justify-between gap-6 border-b border-[var(--ht-hairline)] bg-[var(--ht-surface)] px-4 py-2 md:px-6">
        <AppName />
        {/* one nav: a bar fixed at the bottom below 768px, in the top bar from there up (FR-014) */}
        <nav
          aria-label="Main"
          className="ht-bottom-bar fixed inset-x-0 bottom-0 z-40 flex items-center border-t border-[var(--ht-hairline)] bg-[var(--ht-surface)] md:static md:z-auto md:gap-1 md:border-0 md:bg-transparent"
        >
          {sections.map(({ to, label, end, Icon, ...rest }) => {
            // Jobs also covers the Explore tab, which is not under "/" as far as a path goes
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
                  'ht-nav-link group relative flex min-h-11 flex-1 flex-col items-center justify-center gap-0.5 rounded-md px-1 py-1 text-xs font-medium transition-colors duration-[var(--ht-dur-fast)]',
                  'md:flex-none md:flex-row md:gap-2 md:px-3 md:py-2 md:text-sm',
                  active
                    ? 'text-link md:text-foreground'
                    : 'text-muted-foreground hover:text-link',
                )}
              >
                <Icon
                  aria-hidden
                  className={cn(
                    'size-4 transition-colors duration-[var(--ht-dur-fast)]',
                    active ? 'text-link' : 'group-hover:text-link',
                  )}
                />
                {label}
                {/* the highlight bar: a flat accent line under the current section, grows in on hover */}
                <span
                  aria-hidden
                  className={cn(
                    'absolute inset-x-3 -bottom-2 hidden h-0.5 md:block origin-center rounded-full bg-link transition-transform duration-[var(--ht-dur-enter)]',
                    active ? 'scale-x-100' : 'scale-x-0 group-hover:scale-x-60',
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
      <main className="flex min-h-0 flex-1 flex-col overflow-y-auto pb-[calc(var(--ht-bottom-bar)+5rem)] md:pb-20 scroll-pb-[calc(var(--ht-bottom-bar)+5rem)] md:scroll-pb-20">
        {/* a wide centred column; the chat floats over the page and may cover a little of it */}
        <div
          data-testid="page-column"
          className="ht-page-column mx-auto flex w-full max-w-[1440px] flex-1 flex-col px-4 py-6 md:px-6"
        >
          <Outlet />
        </div>
      </main>
      <MikasaDock />
      <UndoToast />
    </div>
  )
}
