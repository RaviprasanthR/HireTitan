import { cn } from '@/lib/utils'

export type ProgressTone = 'accent' | 'warning' | 'danger'

type Props = {
  /** Spoken name, e.g. "Resume progress". */
  label: string
  /** 0 to 100, or `null` when the amount is not known (an upload in flight). */
  value: number | null
  tone?: ProgressTone
  /** Moving stripes while work is happening; off when paused, failed or finished. */
  animated?: boolean
  className?: string
}

/** The themed progress bar: a slate track, a glowing cyan fill, calm colours for warnings. */
export function ProgressBar({ label, value, tone = 'accent', animated = false, className }: Props) {
  const known = value !== null
  const percent = known ? Math.min(100, Math.max(0, Math.round(value))) : 0
  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={known ? percent : undefined}
      aria-busy={known ? undefined : true}
      data-tone={tone}
      className={cn('ht-progress', className)}
    >
      <div
        data-testid="progress-fill"
        data-indeterminate={known ? undefined : 'true'}
        data-animated={known && animated ? 'true' : undefined}
        className="ht-progress-fill"
        style={known ? { width: `${percent}%` } : undefined}
      />
    </div>
  )
}
