import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const src = resolve(process.cwd(), 'src')
const read = (path: string) => readFileSync(join(src, path), 'utf8')

function files(dir: string, ext: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name)
    if (statSync(path).isDirectory()) return files(path, ext)
    return name.endsWith(ext) && !name.includes('.test.') ? [path] : []
  })
}

describe('type', () => {
  it('test_FR005_figure_utility_uses_mono_tabular', () => {
    const css = read('theme/theme.css')
    const rule = css.slice(css.indexOf('.ht-figure'), css.indexOf('}', css.indexOf('.ht-figure')))
    expect(rule).toContain('font-family: var(--font-mono)')
    expect(rule).toContain('font-variant-numeric: tabular-nums')
  })

  it('test_FR006_no_uppercase_or_tracking_in_theme', () => {
    for (const file of files(src, '.css')) {
      const css = readFileSync(file, 'utf8')
      expect(css, file).not.toMatch(/text-transform:\s*uppercase/)
      for (const [, value] of css.matchAll(/letter-spacing:\s*([\d.]+)em/g)) {
        expect(Number(value), file).toBeLessThanOrEqual(0.01)
      }
    }
    for (const file of files(src, '.tsx')) {
      const tsx = readFileSync(file, 'utf8')
      expect(tsx, file).not.toMatch(/className=[^>]*\b(uppercase|tracking-(wide|wider|widest))\b/)
    }
  })

  it('test_FR006_page_titles_balance', () => {
    expect(read('theme/theme.css')).toMatch(/h1[^{]*\{[^}]*text-wrap:\s*balance/)
  })
})
