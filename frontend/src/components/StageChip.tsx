import type { ReactNode } from 'react'
import { type StageKey, stageOf } from '@/theme/stages'

/** A job's stage as a chip: the stage name in its stage colour (DESIGN.md, "Stage chip"). The label
 * is always text, so colour is never the only signal. */
export function StageChip({ stage, children }: { stage: StageKey; children?: ReactNode }) {
  return (
    <span className="ht-stage-chip" data-stage={stage}>
      {children ?? stageOf(stage).label}
    </span>
  )
}
