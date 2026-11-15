import type { RoundState } from './interviewApi'

export type StatusTone = 'green' | 'yellow' | 'red' | 'blue' | 'teal'

/** The words and colour of a round in the Status column and on its card. Words always show. */
export function roundStatus(state: RoundState, round: number): { label: string; tone: StatusTone } {
  if (state === 'failed') return { label: `Failed in round ${round}`, tone: 'red' }
  if (state === 'cleared') return { label: `Round ${round} cleared`, tone: 'teal' }
  return { label: `Round ${round} scheduled`, tone: 'yellow' }
}
