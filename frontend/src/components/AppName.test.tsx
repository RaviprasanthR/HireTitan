import { render, screen } from '@testing-library/react'
import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { AppName } from './AppName'

describe('AppName', () => {
  it('shows the app name once', () => {
    render(<AppName />)

    expect(screen.getAllByText('HireTitan')).toHaveLength(1)
  })

  it('shows the logo (a pin with a tie) before the name, hidden from screen readers', () => {
    const { container } = render(<AppName />)

    const logo = container.querySelector('svg[data-logo]')
    expect(logo).not.toBeNull()
    expect(logo).toHaveAttribute('aria-hidden', 'true')
    expect(container.firstElementChild?.firstElementChild).toBe(logo?.closest('.ht-logo-3d'))
  })

  it('test_FR003_logo_is_flat_accent', () => {
    const { container } = render(<AppName />)

    const logo = container.querySelector('svg[data-logo]')
    expect(logo?.querySelector('linearGradient')).toBeNull()
    expect(logo?.querySelector('path')).toHaveAttribute('fill', 'var(--ht-accent)')
  })

  it('test_FR003_wordmark_is_solid_text', () => {
    render(<AppName />)

    expect(screen.getByText('HireTitan')).toHaveClass('ht-wordmark')
  })

  it('the tab shows the logo as its icon', () => {
    const html = readFileSync(resolve(process.cwd(), 'index.html'), 'utf8')

    expect(html).toContain('href="/favicon.svg"')
    expect(existsSync(resolve(process.cwd(), 'public/favicon.svg'))).toBe(true)
  })
})

describe('brand.css', () => {
  it('test_FR003_logo_has_no_glow', () => {
    const css = readFileSync(resolve(process.cwd(), 'src/theme/brand.css'), 'utf8')
    expect(css).not.toMatch(/gradient\(|drop-shadow|background-clip|text-fill-color/)
  })

  it('test_FR002_favicon_is_flat_accent', () => {
    const svg = readFileSync(resolve(process.cwd(), 'public/favicon.svg'), 'utf8').toLowerCase()
    expect(svg).not.toContain('gradient')
    expect(svg).toContain('#a99ce6')
  })
})
