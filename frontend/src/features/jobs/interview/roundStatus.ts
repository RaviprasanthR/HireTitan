import type { StageKey } from '@/theme/stages'
import type { RoundState } from './interviewApi'

/** The words and stage of a round in the Status column and on its card. Words always show. */
export function roundStatus(state: RoundState, round: number): { label: string; stage: StageKey } {
  if (state === 'failed') return { label: `Failed in round ${round}`, stage: 'failed' }
  if (state === 'cleared') return { label: `Round ${round} cleared`, stage: 'cleared' }
  return { label: `Round ${round} scheduled`, stage: 'scheduled' }
}
