import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { contrastRatio, tokens } from './tokens'

type HexKey = {
  [K in keyof typeof tokens]: (typeof tokens)[K] extends `#${string}` ? K : never
}[keyof typeof tokens]
type Pair = { fg: HexKey; bg: HexKey; min: number; use: string }

// DESIGN.md: three text roles, one accent with its ink, the field edge. Body text needs 4.5:1;
// a control's boundary needs 3:1 (FR-013).
const grounds: HexKey[] = ['background', 'surface', 'raised']
const pairs: Pair[] = [
  ...grounds.flatMap((bg) =>
    (['text', 'textSecondary', 'textMuted', 'accent'] as const).map((fg) => ({
      fg,
      bg,
      min: 4.5,
      use: `${fg} on ${bg}`,
    })),
  ),
  ...grounds.flatMap((bg) =>
    (['success', 'warning', 'danger'] as const).map((fg) => ({
      fg,
      bg,
      min: 4.5,
      use: `${fg} state text on ${bg}`,
    })),
  ),
]

describe('theme', () => {
  it.each(pairs)('test_FR013_text_roles_meet_AA: $use', ({ fg, bg, min }) => {
    expect(contrastRatio(tokens[fg], tokens[bg])).toBeGreaterThanOrEqual(min)
  })

  it('test_FR013_accent_ink_on_accent', () => {
    expect(contrastRatio(tokens.accentInk, tokens.accent)).toBeGreaterThanOrEqual(4.5)
    expect(contrastRatio(tokens.accentInk, tokens.accentHover)).toBeGreaterThanOrEqual(4.5)
  })

  it('test_FR013_input_edge_3_to_1', () => {
    // Inputs are drawn with the muted text colour as their edge (DESIGN.md, Inputs).
    for (const bg of grounds) {
      expect(contrastRatio(tokens.textMuted, tokens[bg])).toBeGreaterThanOrEqual(3)
    }
  })

  it('test_FR002_no_orange_token', () => {
    const css = readFileSync(resolve(process.cwd(), 'src/theme/theme.css'), 'utf8').toLowerCase()
    expect(css).not.toContain('#f0a35e')
    expect(css).not.toContain('240 163 94')
    expect(Object.values(tokens).map((v) => v.toLowerCase())).not.toContain('#f0a35e')
  })

  it('panels_stand_apart_from_the_page', () => {
    // The theme is flat: a panel is one step lighter than the page, plus a hairline border.
    expect(contrastRatio(tokens.surface, tokens.background)).toBeGreaterThanOrEqual(1.05)
  })

  it('SC007_no_gradient_in_the_theme', () => {
    // Flat colours, except the stripes of the progress bar (an activity indicator) and the accent
    // gradient tokens Ravi allowed on 2026-11-26 for the primary and Mikasa buttons.
    const css = readFileSync(resolve(process.cwd(), 'src/theme/theme.css'), 'utf8').replace(
      /--ht-accent-gradient(-hover)?:[^;]*;/g,
      '',
    )
    expect(css).not.toMatch(/(?<!repeating-)linear-gradient\(/)
    expect(css).not.toMatch(/radial-gradient\(/)
    expect(css).not.toMatch(/conic-gradient\(/)
  })

  it('FR021_no_glow_in_the_theme', () => {
    const css = readFileSync(resolve(process.cwd(), 'src/theme/theme.css'), 'utf8')
    expect(css.toLowerCase()).not.toContain('glow')
  })

  it('brand_css_is_loaded', () => {
    const main = readFileSync(resolve(process.cwd(), 'src/main.tsx'), 'utf8')
    expect(main).toContain("import './theme/brand.css'")
  })

  it('colour_utilities_are_declared_where_tailwind_reads_them', () => {
    // theme.css is imported next to the Tailwind entry file, not through it, so an @theme
    // block there is never processed. These colours are used as text-success, text-danger,
    // text-link, bg-divider and so on, and must be declared in index.css.
    const entry = readFileSync(resolve(process.cwd(), 'src/index.css'), 'utf8')
    for (const name of ['surface', 'raised', 'divider', 'slate', 'muted-small', 'subtle', 'link', 'success', 'warning', 'danger']) {
      expect(entry, `--color-${name}`).toMatch(new RegExp(`--color-${name}\\s*:`))
    }
  })

  it('accent_is_a_real_colour_not_another_grey', () => {
    for (const colour of [tokens.accent]) {
      const n = Number.parseInt(colour.replace('#', ''), 16)
      const channels = [(n >> 16) & 255, (n >> 8) & 255, n & 255]
      // lavender is a soft hue, but still clearly a colour (a grey would be near 0)
      expect(Math.max(...channels) - Math.min(...channels)).toBeGreaterThanOrEqual(60)
    }
  })

  it('FR007 status colours meet contrast', () => {
    // Each pill tone is a token, tinted over the panel: the text must still read at 4.5:1.
    const css = readFileSync(resolve(process.cwd(), 'src/theme/theme.css'), 'utf8')
    const camel = (name: string) => name.replace(/-([a-z])/g, (_, c: string) => c.toUpperCase())
    const rgbOf = (hex: string) => {
      const n = Number.parseInt(hex.replace('#', ''), 16)
      return [(n >> 16) & 255, (n >> 8) & 255, n & 255]
    }
    const hexOf = (c: number[]) => `#${c.map((v) => Math.round(v).toString(16).padStart(2, '0')).join('')}`
    const seen: string[] = []
    for (const [, tone, text, tint, pct] of css.matchAll(
      /\.ht-pill-(\w+)\s*\{\s*color:\s*var\(--ht-([a-z-]+)\);\s*background:\s*color-mix\(in srgb, var\(--ht-([a-z-]+)\) ([\d.]+)%/g,
    )) {
      const fg = tokens[camel(text as string) as HexKey]
      const over = rgbOf(tokens[camel(tint as string) as HexKey])
      const base = rgbOf(tokens.surface)
      const a = Number(pct) / 100
      const background = hexOf(over.map((c, i) => c * a + (base[i] ?? 0) * (1 - a)))
      expect(contrastRatio(fg, background), `pill ${tone}`).toBeGreaterThanOrEqual(4.5)
      seen.push(tone as string)
    }
    for (const tone of ['green', 'yellow', 'red', 'purple', 'grey']) expect(seen).toContain(tone)
  })

  it('contrast_ratio_matches_known_values', () => {
    expect(contrastRatio('#000000', '#ffffff')).toBeCloseTo(21, 1)
    expect(contrastRatio('#777777', '#777777')).toBeCloseTo(1, 5)
  })

})
