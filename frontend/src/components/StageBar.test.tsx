import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { StageBar } from './StageBar'

const counts = { inquired: 1, applied: 2, scheduled: 0, cleared: 0, failed: 1 }

describe('StageBar', () => {
  it('test_FR023_stage_bar_labels_each_stage_once', () => {
    render(<StageBar counts={counts} />)
    for (const label of ['Inquired', 'Applied', 'Interview scheduled', 'Round cleared', 'Failed']) {
      expect(screen.getAllByText(label)).toHaveLength(1)
    }
    expect(screen.getByRole('img')).toHaveAccessibleName(
      '1 inquired, 2 applied, 0 interview scheduled, 0 round cleared, 1 failed',
    )
  })

  it('test_FR023_legend_not_tab_stops', () => {
    const { container } = render(<StageBar counts={counts} />)
    expect(container.querySelectorAll('[tabindex]')).toHaveLength(0)
    expect(container.querySelectorAll('button, a')).toHaveLength(0)
  })

  it('segments_take_their_share_and_skip_empty_stages', () => {
    const { container } = render(<StageBar counts={counts} />)
    const segments = [...container.querySelectorAll<HTMLElement>('[data-segment]')]
    expect(segments.map((s) => s.dataset.segment)).toEqual(['inquired', 'applied', 'failed'])
    expect(segments.map((s) => s.style.flexGrow)).toEqual(['1', '2', '1'])
  })

  it('nothing_to_draw_when_empty', () => {
    const { container } = render(
      <StageBar counts={{ inquired: 0, applied: 0, scheduled: 0, cleared: 0, failed: 0 }} />,
    )
    expect(container).toBeEmptyDOMElement()
  })
})
