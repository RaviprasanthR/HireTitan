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
  // The lightest point of a card (its gradient starts here), so every text colour must hold on it.
  { fg: 'text', bg: 'surfaceHigh', min: 4.5, use: 'body text at the light end of a card' },
  { fg: 'mutedSmall', bg: 'surfaceHigh', min: 4.5, use: 'hint text at the light end of a card' },
  { fg: 'accent', bg: 'surfaceHigh', min: 4.5, use: 'links at the light end of a card' },
  { fg: 'heading', bg: 'surfaceHigh', min: 7, use: 'headings at the light end of a card' },
  { fg: 'danger', bg: 'surfaceHigh', min: 4.5, use: 'error text at the light end of a card' },
  { fg: 'warning', bg: 'surfaceHigh', min: 4.5, use: 'warning text at the light end of a card' },
  { fg: 'success', bg: 'surfaceHigh', min: 4.5, use: 'success text at the light end of a card' },
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
  { fg: 'success', bg: 'divider', min: 3, use: 'the green progress fill on its track' },
  { fg: 'warning', bg: 'surface', min: 3, use: 'status icons on surfaces' },
  { fg: 'danger', bg: 'surface', min: 3, use: 'status icons on surfaces' },
]

describe('theme', () => {
  it.each(pairs)('FR027_text_pairs_meet_WCAG_AA: $fg on $bg ($use)', ({ fg, bg, min }) => {
    expect(contrastRatio(tokens[fg], tokens[bg])).toBeGreaterThanOrEqual(min)
  })

  it('cards_stand_apart_from_the_page', () => {
    // The page runs pageTop, background, pageEnd; the lightest card colour must lift off all of
    // them, and the darkest page colour must be clearly darker than the middle card colour.
    for (const page of [tokens.pageTop, tokens.background, tokens.pageEnd]) {
      expect(contrastRatio(tokens.surfaceHigh, page)).toBeGreaterThanOrEqual(1.2)
    }
    expect(contrastRatio(tokens.surface, tokens.pageEnd)).toBeGreaterThanOrEqual(1.2)
  })

  it('colour_utilities_are_declared_where_tailwind_reads_them', () => {
    // theme.css is imported next to the Tailwind entry file, not through it, so an @theme
    // block there is never processed. These colours are used as text-success, text-danger,
    // text-link, bg-divider and so on, and must be declared in index.css.
    const entry = readFileSync(resolve(process.cwd(), 'src/index.css'), 'utf8')
    for (const name of ['surface', 'divider', 'slate', 'muted-small', 'link', 'success', 'warning', 'danger']) {
      expect(entry, `--color-${name}`).toMatch(new RegExp(`--color-${name}\\s*:`))
    }
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
