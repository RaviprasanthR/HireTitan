import type { tokens } from './tokens'

/** The stages a job moves through, in order (data-model.md, "Pipeline stage"). Keys match the API;
 * each stage has one colour, used the same way on every page (FR-004). */
export type StageKey = 'inquired' | 'applied' | 'scheduled' | 'cleared' | 'failed'

export type Stage = {
  key: StageKey
  label: string
  token: keyof typeof tokens
  cssVar: string
}

export const STAGES: readonly Stage[] = [
  { key: 'inquired', label: 'Inquired', token: 'stageInquired', cssVar: 'var(--ht-stage-inquired)' },
  { key: 'applied', label: 'Applied', token: 'stageApplied', cssVar: 'var(--ht-stage-applied)' },
  {
    key: 'scheduled',
    label: 'Interview scheduled',
    token: 'stageInterview',
    cssVar: 'var(--ht-stage-interview)',
  },
  { key: 'cleared', label: 'Round cleared', token: 'stageCleared', cssVar: 'var(--ht-stage-cleared)' },
  { key: 'failed', label: 'Failed', token: 'stageFailed', cssVar: 'var(--ht-stage-failed)' },
]

export function stageOf(key: StageKey): Stage {
  const stage = STAGES.find((s) => s.key === key)
  if (!stage) throw new Error(`unknown stage ${key}`)
  return stage
}
