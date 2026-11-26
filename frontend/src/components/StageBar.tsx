import { STAGES, type StageKey } from '@/theme/stages'

/**
 * Where the jobs are, as one bar split by stage share, with each stage named once beside it
 * (DESIGN.md, Data display). A picture with a text name; nothing in it takes keyboard focus.
 */
export function StageBar({ counts }: { counts: Record<StageKey, number> }) {
  const total = STAGES.reduce((sum, s) => sum + counts[s.key], 0)
  if (total === 0) return null
  const summary = STAGES.map((s) => `${counts[s.key]} ${s.label.toLowerCase()}`).join(', ')
  return (
    <div className="rounded-[var(--ht-radius-card)] bg-surface p-5">
      <div role="img" aria-label={summary} className="flex h-2 gap-0.5 overflow-hidden rounded-full">
        {STAGES.filter((s) => counts[s.key] > 0).map((s) => (
          <span
            key={s.key}
            data-segment={s.key}
            className="ht-stage-segment"
            style={{ flexGrow: counts[s.key], background: s.cssVar }}
          />
        ))}
      </div>
      <ul aria-hidden className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-sm text-subtle">
        {STAGES.map((s) => (
          <li key={s.key} className="flex items-center gap-2">
            <span className="ht-stage-swatch" style={{ background: s.cssVar }} />
            <span>{s.label}</span>
            <span className="ht-figure text-[var(--ht-text)]">{counts[s.key]}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}
