import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { STAGES, stageOf } from './stages'
import { contrastRatio, tokens } from './tokens'

describe('stages', () => {
  it('test_FR004_five_stages_in_order', () => {
    expect(STAGES.map((s) => s.key)).toEqual([
      'inquired',
      'applied',
      'scheduled',
      'cleared',
      'failed',
    ])
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

  it('test_US2_AS1_applied_same_colour_everywhere', () => {
    const read = (path: string) => readFileSync(resolve(process.cwd(), path), 'utf8')
    const theme = read('src/theme/theme.css')
    const charts = read('src/components/charts.css')
    // every consumer of the stage colours resolves a stage to the one token in stages.ts
    for (const stage of STAGES) {
      const v = stage.cssVar
      expect(theme, 'chip').toContain(
        `.ht-stage-chip[data-stage="${stage.key}"] { --stage: ${v}; }`,
      )
      expect(charts, 'flow').toContain(
        `.ht-flow-step[data-stage="${stage.key}"] .ht-flow-icon { color: ${v}; }`,
      )
    }
    // no tag tone borrows a stage colour (FR-004: a stage colour means only its stage)
    const pills = theme.match(/\.ht-pill-[a-z]+\s*\{[^}]*\}/g) ?? []
    expect(pills.length).toBeGreaterThan(3) // the check below must look at something
    for (const rule of pills) {
      expect(rule).not.toMatch(/--ht-stage-/)
    }
  })
})
