import { Logo } from '@/components/Logo'
import { cn } from '@/lib/utils'

/** The logo and the app name. */
export function AppName({ className }: { className?: string }) {
  return (
    <span className={cn('ht-appname inline-flex items-center gap-2', className)}>
      <Logo className="h-[1.5em]" />
      <span className="ht-wordmark text-xl font-bold tracking-tight">HireTitan</span>
    </span>
  )
}
