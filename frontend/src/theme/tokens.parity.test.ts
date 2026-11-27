import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { tokens } from './tokens'

const kebab = (key: string) => key.replace(/[A-Z]/g, (c) => `-${c.toLowerCase()}`)

describe('tokens', () => {
  it('test_FR001_css_and_ts_tokens_match', () => {
    const css = readFileSync(resolve(process.cwd(), 'src/theme/theme.css'), 'utf8')
    const root = css.slice(css.indexOf(':root'), css.indexOf('}', css.indexOf(':root')))
    for (const [key, value] of Object.entries(tokens)) {
      const m = root.match(new RegExp(`--ht-${kebab(key)}:\\s*([^;]+);`))
      expect(m?.[1]?.trim(), `--ht-${kebab(key)}`).toBe(value)
    }
  })
})
