import { Sparkles } from 'lucide-react'
import { useState } from 'react'
import { cn } from '@/lib/utils'

/** Mikasa's face, cut out to its own shape (transparent around it): local art for this install
 * only (`frontend/public/local/` is gitignored, so the repo never carries third-party art). A fresh
 * clone has no file there and shows the spark. */
export const MIKASA_FACE = '/local/mikasa.png'

/** Mikasa's badge: her cut-out face as it is, or a flat accent disc with a spark (DESIGN.md). */
export function MikasaAvatar({ className }: { className?: string }) {
  const [missing, setMissing] = useState(false)
  if (missing)
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
  return (
    <span aria-hidden className={cn('grid shrink-0 place-items-center', className ?? 'size-7')}>
      <img
        src={MIKASA_FACE}
        alt=""
        draggable={false}
        onError={() => setMissing(true)}
        className="size-full object-contain"
      />
    </span>
  )
}
