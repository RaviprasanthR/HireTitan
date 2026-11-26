import { Sparkles } from 'lucide-react'
import { useState } from 'react'
import { cn } from '@/lib/utils'

/** Mikasa's face: local art for this install only (`frontend/public/local/` is gitignored, so the
 * repo never carries third-party art). A fresh clone has no file there and shows the spark. */
export const MIKASA_FACE = '/local/mikasa.jpg'

/** Mikasa's round badge: her face in a circle, or a flat accent disc with a spark (DESIGN.md). */
export function MikasaAvatar({ className }: { className?: string }) {
  const [missing, setMissing] = useState(false)
  return (
    <span
      aria-hidden
      className={cn(
        'grid shrink-0 place-items-center overflow-hidden rounded-full bg-primary text-primary-foreground',
        className ?? 'size-7',
      )}
    >
      {missing ? (
        <Sparkles className="size-[55%]" />
      ) : (
        // the sticker is wide with the face in the middle: zoom in so the eyes and scarf fill the circle
        <img
          src={MIKASA_FACE}
          alt=""
          draggable={false}
          onError={() => setMissing(true)}
          className="size-full origin-[50%_56%] scale-[1.9] object-cover"
        />
      )}
    </span>
  )
}
