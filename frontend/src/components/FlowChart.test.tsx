import { render, screen, within } from '@testing-library/react'
import { Layers, Send } from 'lucide-react'
import { describe, expect, it } from 'vitest'
import { FlowChart } from './FlowChart'

const steps = [
  { key: 'inquired', icon: Layers, title: 'Inquired', value: '0', stage: 'inquired' as const },
  { key: 'applied', icon: Send, title: 'Applied', value: '2', stage: 'applied' as const },
]

describe('FlowChart', () => {
  it('test_FR024_zero_step_is_muted', () => {
    render(<FlowChart label="Your pipeline" steps={steps} emphasis="applied" />)
    const list = screen.getByRole('list', { name: 'Your pipeline' })
    const [inquired, applied] = within(list).getAllByRole('listitem')
    expect(inquired).toHaveAttribute('data-muted', 'true')
    expect(applied).not.toHaveAttribute('data-muted')
    expect(applied).toHaveAttribute('data-emphasis', 'true')
  })

  it('test_FR024_total_beside_not_a_step', () => {
    render(
      <FlowChart
        label="Your pipeline"
        steps={steps}
        total={{ label: 'In pipeline', value: '2' }}
      />,
    )
    const list = screen.getByRole('list', { name: 'Your pipeline' })
    expect(within(list).queryByText('In pipeline')).toBeNull()
    expect(within(list).getAllByRole('listitem')).toHaveLength(2)
    expect(screen.getByText('In pipeline')).toBeInTheDocument()
  })

  it('test_FR005_counts_are_figures', () => {
    render(<FlowChart label="Your pipeline" steps={steps} />)
    expect(screen.getByText('2')).toHaveClass('ht-figure')
  })

  it('test_FR024_no_icon_rings', () => {
    const { container } = render(<FlowChart label="Your pipeline" steps={steps} />)
    expect(container.querySelector('.ht-flow-node')).toBeNull()
  })

  it('test_FR023a_flow_lays_out_by_its_container', () => {
    render(<FlowChart label="Your pipeline" steps={steps} />)
    const list = screen.getByRole('list', { name: 'Your pipeline' })
    // a row only when its own box is wide, so it stays a column in the overview
    expect(list).toHaveClass('@3xl:flex-row')
    expect(list).not.toHaveClass('lg:flex-row')
    expect(list.closest('[class~="@container"]')).not.toBeNull()
  })
})
