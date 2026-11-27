import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const css = readFileSync('src/theme/theme.css', 'utf-8')
const rule = (selector: string) => {
  const at = css.indexOf(selector)
  expect(at, selector).toBeGreaterThan(-1)
  return css.slice(at, css.indexOf('}', at))
}

describe('the accent gradient (Ravi, 2026-11-26): primary buttons and the Mikasa button only', () => {
  it('is one token pair, used by the primary fills', () => {
    // the token and its hover step (the progress stripes are a repeating gradient, not a blend)
    expect(css.match(/(?<!repeating-)linear-gradient\(/g)).toHaveLength(2)
    const fill = rule('[data-slot="button"][data-variant="default"],')
    expect(fill).toMatch(/\.ht-success-button/)
    expect(fill).toMatch(/\.ht-gradient-fill/)
    expect(fill).toMatch(/background-image: var\(--ht-accent-gradient\)/)
    expect(rule('.ht-gradient-fill:hover')).toMatch(/var\(--ht-accent-gradient-hover\)/)
  })
})

describe('hover colours: the accent, not a lighter white (DESIGN.md)', () => {
  it('secondary and ghost buttons turn lavender with the accent tint', () => {
    for (const hover of [
      '[data-slot="button"][data-variant="outline"]:hover',
      '[data-slot="button"][data-variant="ghost"]:hover',
      '.ht-cancel-button:hover',
    ]) {
      const body = rule(hover)
      expect(body).toMatch(/color: var\(--ht-accent\)/)
      expect(body).toMatch(/background-color: var\(--ht-accent-tint\)/)
    }
  })

  it('ghost buttons rest in the secondary text role', () => {
    expect(rule('[data-slot="button"][data-variant="ghost"] {')).toMatch(
      /color: var\(--ht-text-secondary\)/,
    )
  })

  it('stage buttons take their stage colour, a tint of it on hover', () => {
    expect(rule('.ht-stage-button[data-stage="applied"]')).toMatch(/--ht-stage-applied/)
    expect(rule('.ht-stage-button[data-stage="inquired"]')).toMatch(/--ht-stage-inquired/)
    expect(rule('.ht-stage-button:hover')).toMatch(/color-mix\(in srgb, var\(--stage\)/)
  })
})
