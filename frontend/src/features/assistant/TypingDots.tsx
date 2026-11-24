import { cn } from '@/lib/utils'

/** Three bouncing dots: Mikasa is working on an answer. Announced once to screen readers. */
export function TypingDots({
  label = 'Mikasa is typing',
  className,
}: {
  label?: string
  className?: string
}) {
  return (
    <span
      role="status"
      aria-label={label}
      className={cn('inline-flex items-center gap-1 py-1', className)}
    >
      {[0, 1, 2].map((n) => (
        <span
          key={n}
          aria-hidden
          className="mikasa-dot size-1.5 rounded-full bg-muted-foreground"
          style={{ animationDelay: `${n * 160}ms` }}
        />
      ))}
    </span>
  )
}
