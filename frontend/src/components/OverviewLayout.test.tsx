import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { OverviewLayout } from './OverviewLayout'

describe('OverviewLayout', () => {
  it('test_FR023a_table_first_in_reading_order', () => {
    render(
      <OverviewLayout label="Pipeline overview" overview={<p>chart</p>}>
        <table aria-label="Jobs" />
      </OverviewLayout>,
    )
    const overview = screen.getByRole('complementary', { name: 'Pipeline overview' })
    const table = screen.getByRole('table', { name: 'Jobs' })
    // the table comes first in the DOM; from 1280px the overview is placed in the left column
    expect(table.compareDocumentPosition(overview) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(overview).toHaveClass('ht-overview')
    expect(overview.parentElement).toHaveClass('ht-overview-layout')
    // from 1280px, and only while the overview has something in it, two columns: overview left
    const css = readFileSync(resolve(process.cwd(), 'src/theme/theme.css'), 'utf8')
    const wide = css.slice(css.indexOf('@media (min-width: 80rem)'))
    expect(wide).toMatch(
      /\.ht-overview-layout:has\(> \.ht-overview:not\(:empty\)\)\s*\{\s*grid-template-columns: 22rem minmax\(0, 1fr\)/,
    )
    expect(css).toMatch(/\.ht-overview:empty\s*\{\s*display: none/)
  })

  it('without an overview there is no overview landmark', () => {
    render(
      <OverviewLayout label="Pipeline overview" overview={null}>
        <table aria-label="Jobs" />
      </OverviewLayout>,
    )
    expect(screen.queryByRole('complementary')).toBeNull()
  })
})
