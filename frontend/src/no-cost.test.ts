import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

// SC003 (feature 002d): no screen shows an AI cost, spend or budget. This scans the source of
// every page and component for that wording; comments are ignored, and so are tests, the
// generated API types and the currency list of the Preferences page (pay is not an AI cost).
const ROOT = __dirname
const WORDING = /\b(AI cost|cost so far|budget|spent|spend|monthly cap)\b/i

function sources(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name)
    if (statSync(path).isDirectory()) return sources(path)
    const wanted = /\.tsx?$/.test(name) && !/\.test\.tsx?$|schema\.d\.ts$/.test(name)
    return wanted ? [path] : []
  })
}

function withoutComments(text: string): string {
  return text.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/.*$/gm, '$1')
}

describe('SC003 no cost text', () => {
  it('SC003 no cost text on the search panel, summary, history, profile and setup pages', () => {
    const found = sources(ROOT)
      .filter((path) => WORDING.test(withoutComments(readFileSync(path, 'utf-8'))))
      .map((path) => path.slice(ROOT.length + 1))

    expect(found).toEqual([])
  })
})
