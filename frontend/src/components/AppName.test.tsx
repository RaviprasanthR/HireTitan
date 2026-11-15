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
    expect(container.firstElementChild?.firstElementChild).toBe(logo)
  })

  it('the logo is filled with its own gradient', () => {
    const { container } = render(
      <>
        <AppName />
        <AppName />
      </>,
    )

    const logos = [...container.querySelectorAll('svg[data-logo]')]
    expect(logos).toHaveLength(2)
    const ids = logos.map((logo) => {
      const gradient = logo.querySelector('linearGradient')
      expect(gradient).not.toBeNull()
      expect(logo.querySelector('path')).toHaveAttribute('fill', `url(#${gradient?.id})`)
      return gradient?.id
    })
    // two logos on one page must not share a gradient id
    expect(new Set(ids).size).toBe(2)
  })

  it('the name has the gradient wordmark style, as one text node', () => {
    render(<AppName />)

    expect(screen.getByText('HireTitan')).toHaveClass('ht-wordmark')
  })

  it('the tab shows the logo as its icon', () => {
    const html = readFileSync(resolve(process.cwd(), 'index.html'), 'utf8')

    expect(html).toContain('href="/favicon.svg"')
    expect(existsSync(resolve(process.cwd(), 'public/favicon.svg'))).toBe(true)
  })
})
