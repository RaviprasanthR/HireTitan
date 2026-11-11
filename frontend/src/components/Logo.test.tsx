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

  it('the bolt is one flat colour, with no gradient or glow', () => {
    const { container } = render(<LogoMark />)
    expect(container.querySelectorAll('linearGradient')).toHaveLength(0)
    expect(container.querySelector('svg')?.getAttribute('style') ?? '').not.toContain('drop-shadow')
    expect(container.querySelector('path')).toHaveAttribute('fill', 'var(--ht-logo)')
  })

  it('logo_colour_stands_out_from_the_background (graphics need 3:1, aim far higher)', () => {
    expect(contrastRatio(tokens.logo, tokens.background)).toBeGreaterThanOrEqual(7)
    expect(contrastRatio(tokens.logo, tokens.surface)).toBeGreaterThanOrEqual(7)
  })

  it('the tab icon uses the same theme colours as the in-app logo', () => {
    const favicon = readFileSync(resolve(process.cwd(), 'public/favicon.svg'), 'utf8').toLowerCase()
    expect(favicon).toContain(tokens.logo)
    expect(favicon).toContain(tokens.surface)
    expect(favicon).not.toContain('gradient')
    expect(favicon).not.toContain('#863bff') // the stock purple is gone
  })
})
