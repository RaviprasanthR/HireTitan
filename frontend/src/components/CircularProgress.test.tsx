import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { CircularProgress } from './CircularProgress'

describe('CircularProgress', () => {
  it('names itself, shows the percent and draws the arc in the flat accent (FR-003)', () => {
    const { container } = render(<CircularProgress label="Search progress" value={40} />)
    const bar = screen.getByRole('progressbar', { name: 'Search progress' })
    expect(bar).toHaveAttribute('aria-valuenow', '40')
    expect(bar).toHaveTextContent('40%')
    expect(container.querySelector('linearGradient')).toBeNull()
    expect(container.querySelector('.ht-ring-arc')?.getAttribute('stroke')).toBe('var(--ht-accent)')
  })

  it('spins with no amount when the progress is not known', () => {
    render(<CircularProgress label="Search progress" value={null} />)
    const bar = screen.getByRole('progressbar', { name: 'Search progress' })
    expect(bar).not.toHaveAttribute('aria-valuenow')
    expect(bar).toHaveAttribute('data-indeterminate', 'true')
  })

  it('marks the page as working while it animates, so the logo keeps turning, and clears it after', () => {
    const { rerender, unmount } = render(<CircularProgress label="x" value={10} />)
    expect(document.documentElement).toHaveAttribute('data-working')
    rerender(<CircularProgress label="x" value={10} animated={false} />)
    expect(document.documentElement).not.toHaveAttribute('data-working')
    rerender(<CircularProgress label="x" value={10} />)
    unmount()
    expect(document.documentElement).not.toHaveAttribute('data-working')
  })
})
