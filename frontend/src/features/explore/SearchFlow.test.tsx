import { fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { OutcomeDonut, SearchFlow } from './SearchFlow'

const COUNTS = {
  companiesRead: 3,
  companiesTotal: 3,
  toCheck: 1,
  jobsFound: 40,
  byRules: 25,
  judgedByAi: 12,
  byAi: 4,
  added: 10,
  merged: 3,
}

describe('SearchFlow', () => {
  it('draws the search as round steps joined by connectors', () => {
    render(<SearchFlow counts={COUNTS} />)
    const flow = screen.getByRole('list', { name: 'How the search went' })
    const steps = within(flow).getAllByRole('listitem')
    expect(steps).toHaveLength(5) // the connectors are hidden from assistive technology
    expect(steps[0]).toHaveTextContent(/3 of 3.*Companies read.*1 to check by hand/)
    expect(steps[4]).toHaveTextContent(/10.*New jobs.*3 already known/)
    expect(flow.querySelectorAll('.ht-flow-node')).toHaveLength(5)
    expect(flow.querySelectorAll('.ht-flow-link')).toHaveLength(4)
  })
})

describe('OutcomeDonut', () => {
  it('shows the total in the middle, and a slice when it is pointed at', () => {
    render(<OutcomeDonut added={10} merged={3} leftOut={29} />)
    const donut = screen.getByRole('img', { name: /10 new, 3 already known, 29 left out/ })
    expect(donut.querySelectorAll('[data-part]')).toHaveLength(3)
    const centre = screen.getByTestId('donut-centre')
    expect(centre).toHaveTextContent('42jobs found')

    const leftOut = donut.querySelector('[data-part="leftOut"]') as Element
    fireEvent.mouseEnter(leftOut)

    expect(centre).toHaveTextContent('29Left out69%')
    expect(leftOut).toHaveAttribute('data-state', 'active')
    expect(donut.querySelector('[data-part="added"]')).toHaveAttribute('data-state', 'dimmed')
    fireEvent.mouseLeave(leftOut)
    expect(centre).toHaveTextContent('42jobs found')
  })

  it('the legend highlights its slice from the keyboard too', async () => {
    render(<OutcomeDonut added={10} merged={3} leftOut={29} />)
    const legend = screen.getByRole('list', { name: 'Legend' })
    await userEvent.tab()
    expect(within(legend).getAllByRole('listitem')[0]).toHaveFocus()
    expect(screen.getByTestId('donut-centre')).toHaveTextContent('10New jobs24%')
  })

  it('a tiny slice reads below one percent, not zero', () => {
    render(<OutcomeDonut added={1} merged={142} leftOut={129} />)
    const legend = screen.getByRole('list', { name: 'Legend' })
    expect(within(legend).getByText('New jobs').parentElement).toHaveTextContent('<1%')
  })

  it('a search with no jobs shows an empty ring', () => {
    render(<OutcomeDonut added={0} merged={0} leftOut={0} />)
    expect(screen.getByRole('img', { name: /0 new/ }).querySelectorAll('[data-part]')).toHaveLength(
      0,
    )
  })
})
