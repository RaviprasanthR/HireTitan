import { describe, expect, it } from 'vitest'
import { STAGES, stageOf } from './stages'
import { contrastRatio, tokens } from './tokens'

describe('stages', () => {
  it('test_FR004_five_stages_in_order', () => {
    expect(STAGES.map((s) => s.key)).toEqual(['inquired', 'applied', 'scheduled', 'cleared', 'failed'])
    expect(STAGES.map((s) => s.label)).toEqual([
      'Inquired',
      'Applied',
      'Interview scheduled',
      'Round cleared',
      'Failed',
    ])
  })

  it('test_FR004_each_stage_meets_AA_on_surface_and_raised', () => {
    for (const stage of STAGES) {
      for (const bg of [tokens.surface, tokens.raised]) {
        expect(contrastRatio(tokens[stage.token], bg), stage.key).toBeGreaterThanOrEqual(4.5)
      }
    }
  })

  it('test_FR004_each_stage_has_its_own_colour', () => {
    const colours = STAGES.map((s) => tokens[s.token])
    expect(new Set(colours).size).toBe(STAGES.length)
    for (const s of STAGES) expect(s.cssVar).toMatch(/^var\(--ht-stage-[a-z]+\)$/)
  })

  it('stageOf_finds_a_stage_by_key', () => {
    expect(stageOf('applied').label).toBe('Applied')
  })
})
