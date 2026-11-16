import type { Tone } from './pillTones'

/** A coloured tag. Colour never carries the meaning alone: the words are always shown. */
export function Pill({ tone, children }: { tone: Tone; children: React.ReactNode }) {
  return <span className={`ht-pill ht-pill-${tone}`}>{children}</span>
}
