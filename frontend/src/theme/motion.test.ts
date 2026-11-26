import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative, resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const src = resolve(process.cwd(), 'src')
function files(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name)
    if (statSync(path).isDirectory()) return files(path)
    return /\.(css|tsx)$/.test(name) && !name.includes('.test.') ? [path] : []
  })
}
const all = files(src).map((path) => ({ at: relative(src, path), text: readFileSync(path, 'utf8') }))
const theme = readFileSync(join(src, 'theme/theme.css'), 'utf8')

describe('motion', () => {
  it('test_FR012_no_transition_all', () => {
    const hits = all.filter(({ text }) => /\btransition-all\b|transition:\s*all\b/.test(text))
    expect(hits.map((h) => h.at)).toEqual([])
  })

  it('test_FR012_no_width_or_position_animation', () => {
    const layout = /(?<![-\w])(width|height|top|left|margin[a-z-]*|padding[a-z-]*)(?![-\w])/
    const hits = all.flatMap(({ at, text }) => [
      ...[...text.matchAll(/transition(?:-property)?:([^;]+);/g)]
        .filter((m) => layout.test(m[1] ?? ''))
        .map((m) => `${at}: transition:${m[1]}`),
      ...[...text.matchAll(/@keyframes\s+[\w-]+\s*\{([\s\S]*?)\n\}/g)]
        .filter((m) => /\b(width|height|top|left):/.test(m[1] ?? ''))
        .map(() => `${at}: keyframes`),
    ])
    expect(hits).toEqual([])
  })

  it('test_FR011_focus_ring_has_no_transition', () => {
    const start = theme.search(/^:focus-visible \{/m)
    expect(start).toBeGreaterThan(-1)
    const rule = theme.slice(start, theme.indexOf('}', start))
    expect(rule).toContain('outline: 2px solid var(--ht-accent)')
    expect(rule).toContain('outline-offset: 2px')
    expect(rule).toContain('transition: none')
  })

  it('test_FR012_reduced_motion_stops_animation', () => {
    expect(theme).toMatch(
      /@media \(prefers-reduced-motion: reduce\)\s*\{\s*\*,\s*\*::before,\s*\*::after\s*\{[^}]*animation-duration:\s*0\.01ms !important;[^}]*transition-duration:\s*0\.01ms !important;/,
    )
  })
})
