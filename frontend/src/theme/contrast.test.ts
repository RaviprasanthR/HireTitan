import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { contrastRatio, tokens } from './tokens'

type Pair = { fg: keyof typeof tokens; bg: keyof typeof tokens; min: number; use: string }

// Every text/background pair the UI uses. Body text needs 4.5:1; large text (>= 14px bold or
// >= 18px) and UI components need 3:1. `divider` is decorative only, so it is not listed.
const pairs: Pair[] = [
  { fg: 'text', bg: 'background', min: 4.5, use: 'body text on the page' },
  { fg: 'text', bg: 'surface', min: 4.5, use: 'text on cards, sidebar, inputs' },
  { fg: 'text', bg: 'primary', min: 4.5, use: 'button text, active nav' },
  { fg: 'mutedSmall', bg: 'background', min: 4.5, use: 'small hint and label text' },
  { fg: 'mutedSmall', bg: 'surface', min: 3, use: 'hint text on surfaces (large only)' },
  { fg: 'muted', bg: 'background', min: 3, use: 'icons, input outlines, muted text >= 14px' },
  { fg: 'accent', bg: 'background', min: 4.5, use: 'links' },
  // accent on surface is 4.46:1: under the 4.5 bar for small text, so on cards the accent is
  // for the focus ring and large text only, and small links there use `text` with an underline.
  { fg: 'accent', bg: 'surface', min: 3, use: 'focus ring and large text on surfaces' },
  { fg: 'success', bg: 'background', min: 4.5, use: 'success badge text' },
  { fg: 'warning', bg: 'background', min: 4.5, use: 'warning badge text' },
  { fg: 'danger', bg: 'background', min: 4.5, use: 'error and danger text' },
  { fg: 'success', bg: 'surface', min: 3, use: 'status icons on surfaces' },
  { fg: 'warning', bg: 'surface', min: 3, use: 'status icons on surfaces' },
  { fg: 'danger', bg: 'surface', min: 3, use: 'status icons on surfaces' },
]

describe('theme', () => {
  it.each(pairs)('FR027_text_pairs_meet_WCAG_AA: $fg on $bg ($use)', ({ fg, bg, min }) => {
    expect(contrastRatio(tokens[fg], tokens[bg])).toBeGreaterThanOrEqual(min)
  })

  it('contrast_ratio_matches_known_values', () => {
    expect(contrastRatio('#000000', '#ffffff')).toBeCloseTo(21, 1)
    expect(contrastRatio('#777777', '#777777')).toBeCloseTo(1, 5)
  })

  it('theme_css_defines_every_token_colour', () => {
    const css = readFileSync(resolve(process.cwd(), 'src/theme/theme.css'), 'utf8').toLowerCase()
    for (const colour of Object.values(tokens)) {
      expect(css).toContain(colour.toLowerCase())
    }
  })
})
