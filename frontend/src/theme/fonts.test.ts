import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const src = resolve(process.cwd(), 'src')

function cssFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name)
    if (statSync(path).isDirectory()) return cssFiles(path)
    return name.endsWith('.css') ? [path] : []
  })
}

describe('fonts', () => {
  it('test_R3_mono_face_bundled_locally', () => {
    const index = readFileSync(join(src, 'index.css'), 'utf8')
    expect(index).toContain('@import "@fontsource-variable/geist-mono"')
  })

  it('test_FR030_no_font_loaded_from_another_host', () => {
    for (const file of cssFiles(src)) {
      const css = readFileSync(file, 'utf8')
      expect(css, file).not.toMatch(/@import\s+url\(\s*['"]?https?:/)
      expect(css, file).not.toMatch(/src:\s*url\(\s*['"]?https?:/)
    }
  })
})
