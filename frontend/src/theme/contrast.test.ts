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
  { fg: 'onPrimary', bg: 'primary', min: 4.5, use: 'button text, active nav (gradient start)' },
  { fg: 'onPrimary', bg: 'primaryEnd', min: 4.5, use: 'button text, active nav (gradient end)' },
  { fg: 'mutedSmall', bg: 'background', min: 4.5, use: 'small hint and label text' },
  { fg: 'mutedSmall', bg: 'surface', min: 3, use: 'hint text on surfaces (large only)' },
  { fg: 'muted', bg: 'background', min: 3, use: 'icons, input outlines, muted text >= 14px' },
  { fg: 'accent', bg: 'background', min: 4.5, use: 'links' },
  { fg: 'accent', bg: 'surface', min: 4.5, use: 'links and focus ring on surfaces' },
  { fg: 'text', bg: 'divider', min: 4.5, use: 'text on hover and muted fills' },
  { fg: 'heading', bg: 'background', min: 7, use: 'headings on the page' },
  { fg: 'heading', bg: 'surface', min: 7, use: 'headings on cards' },
  { fg: 'heading', bg: 'divider', min: 7, use: 'headings at the top of the page gradient' },
  { fg: 'primary', bg: 'background', min: 3, use: 'button and progress fill against the page' },
  { fg: 'primary', bg: 'surface', min: 3, use: 'button and progress fill against cards' },
  // `divider` and `slate` are decorative only (slate on the page is 2.7:1), so neither is
  // used for text, outlines or icons.
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

  it('accent_is_a_real_colour_not_another_grey', () => {
    for (const colour of [tokens.primary, tokens.primaryEnd, tokens.accent, tokens.logoEnd]) {
      const n = Number.parseInt(colour.replace('#', ''), 16)
      const channels = [(n >> 16) & 255, (n >> 8) & 255, n & 255]
      expect(Math.max(...channels) - Math.min(...channels)).toBeGreaterThanOrEqual(100)
    }
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
