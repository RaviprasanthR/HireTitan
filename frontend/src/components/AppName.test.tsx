import { render, screen } from '@testing-library/react'
import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { AppName } from './AppName'

describe('AppName', () => {
  it('shows the app name once, as plain text', () => {
    render(<AppName />)

    expect(screen.getAllByText('HireTitan')).toHaveLength(1)
  })

  it('has no logo or other graphic', () => {
    const { container } = render(<AppName />)

    expect(container.querySelector('svg')).toBeNull()
    expect(container.querySelector('img')).toBeNull()
  })

  it('the tab has no logo icon either', () => {
    const html = readFileSync(resolve(process.cwd(), 'index.html'), 'utf8')

    expect(html).not.toContain('favicon.svg')
    expect(existsSync(resolve(process.cwd(), 'public/favicon.svg'))).toBe(false)
  })
})
