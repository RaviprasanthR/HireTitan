import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative, resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const src = resolve(process.cwd(), 'src')

function files(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name)
    if (statSync(path).isDirectory()) return name === 'api' ? [] : files(path)
    if (!/\.(css|ts|tsx)$/.test(name) || /\.test\.|\.d\.ts$/.test(name)) return []
    return name === 'tokens.ts' ? [] : [path]
  })
}

/** The source with the token block (theme.css :root) and comments cut out. */
function scanned(path: string): string {
  let text = readFileSync(path, 'utf8')
  if (path.endsWith(join('theme', 'theme.css'))) {
    const start = text.indexOf(':root')
    text = text.slice(0, start) + text.slice(text.indexOf('}', start) + 1)
  }
  return text.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '')
}

const COLOUR = /#[0-9a-fA-F]{3,8}\b(?![-\w])|\b(?:rgba?|hsla?|oklch)\(\s*\d|-\[(?:#|rgb|hsl)/

describe('colour guard', () => {
  it('test_FR001_no_colour_literal_outside_tokens', () => {
    const hits = files(src).flatMap((path) =>
      scanned(path)
        .split('\n')
        .map((line, i) => ({ line, at: `${relative(src, path)}:${i + 1}` }))
        .filter(({ line }) => COLOUR.test(line))
        .map(({ line, at }) => `${at}  ${line.trim()}`),
    )
    expect(hits).toEqual([])
  })

  it('test_FR003_no_gradient_or_glow_anywhere', () => {
    const banned =
      /(?<!repeating-)linear-gradient\(|radial-gradient\(|conic-gradient\(|drop-shadow|bg-gradient-|shadow-\[0_0_[1-9]/
    const hits = files(src)
      // the accent gradient tokens are the one allowed blend (Ravi, 2026-11-26)
      .filter((path) => banned.test(scanned(path).replace(/--ht-accent-gradient(-hover)?:[^;]*;/g, '')))
      .map((path) => relative(src, path))
    expect(hits).toEqual([])
  })
})
