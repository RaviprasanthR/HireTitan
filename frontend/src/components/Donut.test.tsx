import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { Donut } from './Donut'

describe('Donut', () => {
  it('each slice is a soft gradient of its own colour (Ravi, 2026-11-26)', () => {
    const { container } = render(
      <Donut
        caption="Jobs"
        totalLabel="jobs"
        ariaLabel="2 applied, 1 inquired"
        parts={[
          { key: 'applied', label: 'Applied', value: 2, colour: 'var(--ht-stage-applied)' },
          { key: 'inquired', label: 'Inquired', value: 1, colour: 'var(--ht-stage-inquired)' },
        ]}
      />,
    )
    const slice = container.querySelector('[data-part="applied"]') as SVGElement
    const id = /^url\(#(.+)\)$/.exec(slice.getAttribute('stroke') ?? '')?.[1]
    const gradient = container.querySelector(`linearGradient[id="${id}"]`) as SVGElement
    const stops = [...gradient.querySelectorAll('stop')].map((s) => s.getAttribute('stop-color'))
    // from the stage colour itself to a lighter step of the same colour, so its meaning holds
    expect(stops[0]).toBe('var(--ht-stage-applied)')
    expect(stops[1]).toMatch(/color-mix\(in srgb, var\(--ht-stage-applied\)/)
    // the legend dot stays the plain colour
    const dot = container.querySelector('li span[aria-hidden]') as HTMLElement
    expect(dot.style.backgroundColor).toBe('var(--ht-stage-applied)')
  })
})
