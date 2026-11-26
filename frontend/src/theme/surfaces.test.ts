import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const css = readFileSync(resolve(process.cwd(), 'src/theme/theme.css'), 'utf8')
const rule = (selector: string) => {
  // a selector at the start of a line opens (or begins the list of) a rule
  const start = css.indexOf(`\n${selector}`) + 1
  expect(start, selector).toBeGreaterThan(0)
  return css.slice(start, css.indexOf('}', start))
}

describe('surfaces', () => {
  it('test_FR009_no_side_stripe_rules', () => {
    expect(css).not.toMatch(/border-left:\s*[2-9]px/)
    expect(css).not.toMatch(/^\.ht-[\w-]+\s*\{\s*--accent:/m)
  })

  it('test_FR009_one_card_recipe', () => {
    const card = rule('.ht-card,')
    for (const selector of ['.ht-card,', '.ht-detail-card,', '.ht-search-panel {']) {
      expect(card.slice(0, card.indexOf('{') + 1)).toContain(selector)
    }
    expect(card).toContain('background: var(--ht-surface)')
    expect(card).toContain('border: 1px solid var(--ht-hairline)')
    expect(card).toContain('border-radius: var(--ht-radius-card)')
    expect(card).not.toMatch(/box-shadow/)
  })

  it('test_FR015_overflow_clip_on_root', () => {
    expect(rule('html,')).toContain('overflow-x: clip')
  })

  it('test_FR016_table_cards_pattern_defined', () => {
    const media = css.slice(css.indexOf('@media (max-width: 767.98px)'))
    expect(media).toContain('.ht-table-cards thead')
    expect(media).toContain('.ht-table-cards tr')
    expect(media).toContain('td[data-label]::before')
  })

  it('selection_is_themed', () => {
    expect(rule('::selection')).toContain('var(--ht-accent-tint)')
  })
})
