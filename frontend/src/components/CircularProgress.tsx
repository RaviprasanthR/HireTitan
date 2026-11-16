import { useId } from 'react'
import { cn } from '@/lib/utils'

type Props = {
  /** Spoken name, e.g. "Search progress". */
  label: string
  /** 0 to 100, or `null` when the amount is not known: the ring then just spins. */
  value: number | null
  /** Spinning while work is happening; still when stopping. */
  animated?: boolean
  className?: string
}

const RADIUS = 26
const CIRCUMFERENCE = 2 * Math.PI * RADIUS

/** A ring with a colour-changing arc that fills as the work goes, with the percent in the middle; unknown amount: a spinning arc. */
export function CircularProgress({ label, value, animated = true, className }: Props) {
  const known = value !== null
  const percent = known ? Math.min(100, Math.max(0, Math.round(value))) : 0
  const gradient = `ht-ring-gradient-${useId().replace(/:/g, '')}`
  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={known ? percent : undefined}
      aria-busy={known ? undefined : true}
      className={cn('ht-ring', className)}
      data-animated={animated ? 'true' : undefined}
      data-indeterminate={known ? undefined : 'true'}
    >
      <svg viewBox="0 0 64 64" aria-hidden className="ht-ring-svg">
        <defs>
          {/* orange to pink to violet to cyan: the arc changes colour along its length */}
          <linearGradient id={gradient} x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="#f0a35e" />
            <stop offset="35%" stopColor="#f2688f" />
            <stop offset="70%" stopColor="#a371f7" />
            <stop offset="100%" stopColor="#4cc9f0" />
          </linearGradient>
        </defs>
        <circle cx="32" cy="32" r={RADIUS} className="ht-ring-track" />
        <circle
          cx="32"
          cy="32"
          r={RADIUS}
          className="ht-ring-arc"
          stroke={`url(#${gradient})`}
          strokeDasharray={CIRCUMFERENCE}
          strokeDashoffset={known ? CIRCUMFERENCE * (1 - percent / 100) : CIRCUMFERENCE * 0.72}
        />
      </svg>
      {known && (
        <span aria-hidden className="ht-ring-label">
          {percent}%
        </span>
      )}
    </div>
  )
}
