import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ProgressBar } from './ProgressBar'

describe('ProgressBar', () => {
  it('shows a known value to assistive technology and as the fill width', () => {
    render(<ProgressBar label="Resume progress" value={40} />)
    const bar = screen.getByRole('progressbar', { name: 'Resume progress' })
    expect(bar).toHaveAttribute('aria-valuemin', '0')
    expect(bar).toHaveAttribute('aria-valuemax', '100')
    expect(bar).toHaveAttribute('aria-valuenow', '40')
    expect(screen.getByTestId('progress-fill')).toHaveStyle({ width: '40%' })
  })

  it('clamps values outside 0 to 100', () => {
    const { rerender } = render(<ProgressBar label="p" value={140} />)
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '100')
    rerender(<ProgressBar label="p" value={-5} />)
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '0')
  })

  it('without a value it is indeterminate: no aria-valuenow, marked busy', () => {
    render(<ProgressBar label="Uploading your resume" value={null} />)
    const bar = screen.getByRole('progressbar', { name: 'Uploading your resume' })
    expect(bar).not.toHaveAttribute('aria-valuenow')
    expect(bar).toHaveAttribute('aria-busy', 'true')
    expect(screen.getByTestId('progress-fill')).toHaveAttribute('data-indeterminate', 'true')
  })

  it('tone is exposed for the theme to colour (warning when paused, danger when failed)', () => {
    const { rerender } = render(<ProgressBar label="p" value={50} />)
    expect(screen.getByRole('progressbar')).toHaveAttribute('data-tone', 'accent')
    rerender(<ProgressBar label="p" value={50} tone="warning" />)
    expect(screen.getByRole('progressbar')).toHaveAttribute('data-tone', 'warning')
    rerender(<ProgressBar label="p" value={50} tone="danger" />)
    expect(screen.getByRole('progressbar')).toHaveAttribute('data-tone', 'danger')
  })
})
