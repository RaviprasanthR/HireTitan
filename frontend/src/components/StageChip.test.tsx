import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { StageChip } from './StageChip'

describe('StageChip', () => {
  it('test_FR004_chip_shows_label_text', () => {
    render(<StageChip stage="scheduled" />)
    const chip = screen.getByText('Interview scheduled')
    expect(chip).toHaveClass('ht-stage-chip')
    expect(chip).toHaveAttribute('data-stage', 'scheduled')
  })

  it('a custom label keeps the stage colour', () => {
    render(<StageChip stage="cleared">Round 2 cleared</StageChip>)
    expect(screen.getByText('Round 2 cleared')).toHaveAttribute('data-stage', 'cleared')
  })
})
