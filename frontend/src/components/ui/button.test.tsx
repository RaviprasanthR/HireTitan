import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { Button } from './button'

describe('button variants (FR-010)', () => {
  it('test_FR010_button_variants', () => {
    const { rerender } = render(<Button>Save</Button>)
    const button = screen.getByRole('button', { name: 'Save' })
    expect(button).toHaveClass('bg-primary', 'h-9')
    expect(button.className).not.toMatch(/transition-all/)
    expect(button.className).toMatch(/active:[^ ]*scale-\[0\.98\]/)
    rerender(<Button variant="outline">Back</Button>)
    expect(screen.getByRole('button', { name: 'Back' })).toHaveClass('border-slate')
  })
})

describe('button colours: save is the primary, cancel is secondary, delete is red', () => {
  it.each([
    ['success', 'ht-success-button'],
    ['cancel', 'ht-cancel-button'],
    ['danger', 'ht-danger-button'],
  ] as const)('the %s variant uses %s', (variant, cls) => {
    render(<Button variant={variant}>Go</Button>)

    expect(screen.getByRole('button', { name: 'Go' })).toHaveClass(cls)
  })

  it('the cancel button takes the accent tint on hover and stays still for reduced motion', () => {
    const css = readFileSync('src/theme/theme.css', 'utf-8')

    expect(css).toMatch(/\.ht-cancel-button:hover:not\(:disabled\)\s*\{[^}]*var\(--ht-accent-tint\)/)
    expect(css).toMatch(/prefers-reduced-motion[^}]*\{[^}]*\.ht-cancel-button/)
  })
})
