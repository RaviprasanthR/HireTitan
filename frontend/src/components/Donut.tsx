import { useEffect, useState } from 'react'
import './charts.css'

export type DonutPart = { key: string; label: string; value: number; colour: string }

const SIZE = 168
const RADIUS = 64
const STROKE = 18
const CIRCUMFERENCE = 2 * Math.PI * RADIUS
const GAP = 3 // the surface shows between slices

/**
 * Parts of a whole as a donut, with the total in the middle and a legend that names each slice,
 * its count and share (so colour is never the only cue). The slices draw themselves in; pointing
 * at a slice or its legend entry (or focusing the entry) widens it, dims the others and puts its
 * numbers in the middle. Colours come from the caller and must pass the dataviz palette check.
 */
export function Donut({
  parts,
  caption,
  totalLabel,
  ariaLabel,
}: {
  parts: DonutPart[]
  caption: string
  totalLabel: string
  ariaLabel: string
}) {
  const [grown, setGrown] = useState(false)
  const [active, setActive] = useState<string | null>(null)
  useEffect(() => {
    const frame = requestAnimationFrame(() => setGrown(true))
    return () => cancelAnimationFrame(frame)
  }, [])

  const total = parts.reduce((sum, part) => sum + part.value, 0)
  const share = (value: number) => (total === 0 ? 0 : value / total)
  const percent = (value: number) => {
    const rounded = Math.round(share(value) * 100)
    return value > 0 && rounded === 0 ? '<1' : String(rounded)
  }
  const shown = parts.find((part) => part.key === active)
  const state = (key: string) => (active === null ? 'idle' : active === key ? 'active' : 'dimmed')
  const pointer = (key: string) => ({
    onMouseEnter: () => setActive(key),
    onMouseLeave: () => setActive(null),
  })

  const drawn = parts.filter((part) => part.value > 0)
  const gap = drawn.length > 1 ? GAP : 0
  // where each slice starts on the ring: the shares of the slices before it
  const lengths = drawn.map((part) => share(part.value) * CIRCUMFERENCE)
  const slices = drawn.map((part, index) => ({
    ...part,
    start: lengths.slice(0, index).reduce((sum, length) => sum + length, 0),
    length: Math.max((lengths[index] ?? 0) - gap, 1),
  }))

  return (
    <figure className="flex flex-wrap items-center gap-5 rounded-lg bg-surface p-4">
      <div className="relative shrink-0" style={{ width: SIZE, height: SIZE }}>
        <svg
          role="img"
          aria-label={ariaLabel}
          viewBox={`0 0 ${SIZE} ${SIZE}`}
          width={SIZE}
          height={SIZE}
          className="-rotate-90"
        >
          <circle
            cx={SIZE / 2}
            cy={SIZE / 2}
            r={RADIUS}
            fill="none"
            stroke="var(--ht-hairline)"
            strokeWidth={STROKE}
          />
          {slices.map((slice) => (
            <circle
              key={slice.key}
              data-part={slice.key}
              data-state={state(slice.key)}
              className="ht-donut-slice"
              cx={SIZE / 2}
              cy={SIZE / 2}
              r={RADIUS}
              fill="none"
              stroke={slice.colour}
              strokeWidth={STROKE}
              strokeDasharray={`${grown ? slice.length : 0} ${CIRCUMFERENCE}`}
              strokeDashoffset={-slice.start}
              {...pointer(slice.key)}
            />
          ))}
        </svg>
        <div
          aria-hidden
          data-testid="donut-centre"
          className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center text-center"
        >
          <span key={shown?.key ?? 'total'} className="ht-donut-readout block">
            <span className="block text-2xl font-semibold">{shown ? shown.value : total}</span>
            <span className="block max-w-24 text-xs leading-tight text-muted-small">
              {shown ? shown.label : totalLabel}
            </span>
            {shown && (
              <span className="block text-xs text-muted-small">{percent(shown.value)}%</span>
            )}
          </span>
        </div>
      </div>
      <div className="min-w-0 space-y-2">
        <figcaption className="text-sm text-muted-small">{caption}</figcaption>
        <ul aria-label="Legend" className="space-y-1 text-sm">
          {parts.map((part) => (
            <li
              key={part.key}
              tabIndex={0}
              data-state={state(part.key)}
              className="ht-donut-legend flex items-center gap-2 rounded-md px-2 py-1"
              onFocus={() => setActive(part.key)}
              onBlur={() => setActive(null)}
              {...pointer(part.key)}
            >
              <span
                aria-hidden
                className="inline-block size-3 rounded-full"
                style={{ backgroundColor: part.colour }}
              />
              <span>{part.label}</span>
              <span className="font-semibold">{part.value}</span>
              <span className="text-muted-small">{percent(part.value)}%</span>
            </li>
          ))}
        </ul>
      </div>
    </figure>
  )
}
