import { cn } from '@/lib/utils'

/** The app name, plain text: there is no logo or other graphic. */
export function AppName({ className }: { className?: string }) {
  return (
    <span className={cn('text-xl font-semibold tracking-tight text-heading', className)}>
      HireTitan
    </span>
  )
}
