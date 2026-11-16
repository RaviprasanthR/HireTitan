import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { CircularProgress } from './CircularProgress'

describe('CircularProgress', () => {
  it('names itself, shows the percent and colours the arc with its own gradient', () => {
    const { container } = render(<CircularProgress label="Search progress" value={40} />)
    const bar = screen.getByRole('progressbar', { name: 'Search progress' })
    expect(bar).toHaveAttribute('aria-valuenow', '40')
    expect(bar).toHaveTextContent('40%')
    const id = container.querySelector('linearGradient')?.getAttribute('id')
    expect(id).toBeTruthy()
    expect(container.querySelector('.ht-ring-arc')?.getAttribute('stroke')).toBe(`url(#${id})`)
  })

  it('spins with no amount when the progress is not known', () => {
    render(<CircularProgress label="Search progress" value={null} />)
    const bar = screen.getByRole('progressbar', { name: 'Search progress' })
    expect(bar).not.toHaveAttribute('aria-valuenow')
    expect(bar).toHaveAttribute('data-indeterminate', 'true')
  })

  it('gives each ring its own gradient id', () => {
    const { container } = render(
      <>
        <CircularProgress label="One" value={10} />
        <CircularProgress label="Two" value={20} />
      </>,
    )
    const ids = [...container.querySelectorAll('linearGradient')].map((g) => g.id)
    expect(new Set(ids).size).toBe(2)
  })
})
