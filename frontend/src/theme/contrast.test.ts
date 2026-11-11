import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { contrastRatio, tokens } from './tokens'

type Pair = { fg: keyof typeof tokens; bg: keyof typeof tokens; min: number; use: string }

// Every text/background pair the UI uses (FR-021). Body text needs 4.5:1; large text (>= 14px
// bold or >= 18px) and UI components need 3:1. `divider` and `slate` are decorative (borders,
// fills), never text.
const pairs: Pair[] = [
  { fg: 'text', bg: 'background', min: 4.5, use: 'body text on the page' },
  { fg: 'text', bg: 'surface', min: 4.5, use: 'text on panels, sidebar, inputs' },
  { fg: 'text', bg: 'divider', min: 4.5, use: 'text on hover and muted fills' },
  { fg: 'heading', bg: 'background', min: 7, use: 'headings on the page' },
  { fg: 'heading', bg: 'surface', min: 7, use: 'headings on panels' },
  { fg: 'heading', bg: 'divider', min: 7, use: 'headings on hover fills' },
  { fg: 'mutedSmall', bg: 'background', min: 4.5, use: 'small hint and label text' },
  { fg: 'mutedSmall', bg: 'surface', min: 4.5, use: 'hint text on panels' },
  { fg: 'muted', bg: 'background', min: 4.5, use: 'icons, input outlines, muted text' },
  { fg: 'accent', bg: 'background', min: 4.5, use: 'links, active menu item' },
  { fg: 'accent', bg: 'surface', min: 4.5, use: 'links and focus ring on panels' },
  { fg: 'onPrimary', bg: 'primary', min: 4.5, use: 'chip and button text, active nav' },
  { fg: 'primary', bg: 'background', min: 1.1, use: 'a chip is visible against the page' },
  { fg: 'success', bg: 'background', min: 4.5, use: 'success badge text' },
  { fg: 'warning', bg: 'background', min: 4.5, use: 'warning badge text' },
  { fg: 'danger', bg: 'background', min: 4.5, use: 'error and danger text' },
  { fg: 'success', bg: 'surface', min: 4.5, use: 'success text on panels' },
  { fg: 'warning', bg: 'surface', min: 4.5, use: 'warning text on panels' },
  { fg: 'danger', bg: 'surface', min: 4.5, use: 'error text on panels' },
  { fg: 'success', bg: 'divider', min: 3, use: 'the green progress fill on its track' },
]

describe('theme', () => {
  it.each(pairs)('FR021_text_pairs_meet_WCAG_AA: $fg on $bg ($use)', ({ fg, bg, min }) => {
    expect(contrastRatio(tokens[fg], tokens[bg])).toBeGreaterThanOrEqual(min)
  })

  it('panels_stand_apart_from_the_page', () => {
    // The theme is flat: a panel is one step lighter than the page, plus a hairline border.
    expect(contrastRatio(tokens.surface, tokens.background)).toBeGreaterThanOrEqual(1.05)
  })

  it('SC007_no_gradient_in_the_theme', () => {
    // Flat colours only. The one allowed exception is the moving stripes of the progress bar,
    // an activity indicator (repeating-linear-gradient), not a colour blend.
    const css = readFileSync(resolve(process.cwd(), 'src/theme/theme.css'), 'utf8')
    expect(css).not.toMatch(/(?<!repeating-)linear-gradient\(/)
    expect(css).not.toMatch(/radial-gradient\(/)
    expect(css).not.toMatch(/conic-gradient\(/)
  })

  it('FR021_no_glow_in_the_theme', () => {
    const css = readFileSync(resolve(process.cwd(), 'src/theme/theme.css'), 'utf8')
    expect(css.toLowerCase()).not.toContain('glow')
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
    for (const colour of [tokens.accent]) {
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
