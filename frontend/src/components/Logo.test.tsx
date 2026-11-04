import { render, screen } from '@testing-library/react'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { contrastRatio, tokens } from '@/theme/tokens'
import { LogoMark, Wordmark } from './Logo'

describe('Logo', () => {
  it('the bolt mark is decorative: hidden from screen readers', () => {
    const { container } = render(<LogoMark />)
    const svg = container.querySelector('svg')
    expect(svg).not.toBeNull()
    expect(svg).toHaveAttribute('aria-hidden', 'true')
  })

  it('the wordmark names the app once, as text', () => {
    render(<Wordmark />)
    expect(screen.getAllByText('HireTitan')).toHaveLength(1)
  })

  it('two marks on one page do not share gradient ids', () => {
    const { container } = render(
      <>
        <LogoMark />
        <LogoMark />
      </>,
    )
    const ids = [...container.querySelectorAll('linearGradient')].map((g) => g.id)
    expect(new Set(ids).size).toBe(ids.length)
    expect(ids.length).toBe(2)
  })

  it('logo_colours_stand_out_from_the_background (graphics need 3:1, aim far higher)', () => {
    expect(contrastRatio(tokens.logo, tokens.background)).toBeGreaterThanOrEqual(7)
    expect(contrastRatio(tokens.logoEnd, tokens.background)).toBeGreaterThanOrEqual(7)
    expect(contrastRatio(tokens.logo, tokens.surface)).toBeGreaterThanOrEqual(7)
    expect(contrastRatio(tokens.logoEnd, tokens.surface)).toBeGreaterThanOrEqual(4.5)
  })

  it('the tab icon uses the same theme colours as the in-app logo', () => {
    const favicon = readFileSync(resolve(process.cwd(), 'public/favicon.svg'), 'utf8').toLowerCase()
    expect(favicon).toContain(tokens.logo)
    expect(favicon).toContain(tokens.logoEnd)
    expect(favicon).not.toContain('#863bff') // the stock purple is gone
  })
})
