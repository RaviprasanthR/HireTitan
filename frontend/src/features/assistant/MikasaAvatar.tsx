import { Sparkles } from 'lucide-react'
import { cn } from '@/lib/utils'

/** Mikasa's round badge: the Titan blue to lilac gradient with a spark. */
export function MikasaAvatar({ className }: { className?: string }) {
  return (
    <span
      aria-hidden
      className={cn(
        'grid shrink-0 place-items-center rounded-full bg-primary text-primary-foreground',
        className ?? 'size-7',
      )}
    >
      <Sparkles className="size-[55%]" />
    </span>
  )
}
