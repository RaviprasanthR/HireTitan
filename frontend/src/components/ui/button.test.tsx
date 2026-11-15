import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { Button } from './button'

describe('button colours: save is green, cancel is orange, delete is red', () => {
  it.each([
    ['success', 'ht-success-button'],
    ['cancel', 'ht-cancel-button'],
    ['danger', 'ht-danger-button'],
  ] as const)('the %s variant uses %s', (variant, cls) => {
    render(<Button variant={variant}>Go</Button>)

    expect(screen.getByRole('button', { name: 'Go' })).toHaveClass(cls)
  })

  it('the cancel button turns orange on hover and stays still for reduced motion', () => {
    const css = readFileSync('src/theme/theme.css', 'utf-8')

    expect(css).toMatch(/\.ht-cancel-button:hover:not\(:disabled\)\s*\{[^}]*#f0a35e/)
    expect(css).toMatch(/prefers-reduced-motion[^}]*\{[^}]*\.ht-cancel-button/)
  })
})
