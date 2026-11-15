import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { HIDE_AFTER_MS, installAutoHideScrollbars } from './scrollbars'

describe('auto-hiding scrollbars', () => {
  let stop: () => void

  beforeEach(() => {
    vi.useFakeTimers()
    stop = installAutoHideScrollbars()
  })
  afterEach(() => {
    stop()
    vi.useRealTimers()
    document.body.innerHTML = ''
    document.documentElement.removeAttribute('data-scrolling')
  })

  it('marks a scrolled area while it scrolls and clears the mark soon after', () => {
    const list = document.createElement('div')
    document.body.append(list)

    list.dispatchEvent(new Event('scroll')) // scroll does not bubble: the listener captures it

    expect(list).toHaveAttribute('data-scrolling')
    vi.advanceTimersByTime(HIDE_AFTER_MS - 1)
    expect(list).toHaveAttribute('data-scrolling')
    vi.advanceTimersByTime(2)
    expect(list).not.toHaveAttribute('data-scrolling')
  })

  it('keeps the mark while scrolling continues', () => {
    const list = document.createElement('div')
    document.body.append(list)

    list.dispatchEvent(new Event('scroll'))
    vi.advanceTimersByTime(HIDE_AFTER_MS - 100)
    list.dispatchEvent(new Event('scroll')) // still moving: the wait starts again
    vi.advanceTimersByTime(HIDE_AFTER_MS - 100)

    expect(list).toHaveAttribute('data-scrolling')
    vi.advanceTimersByTime(200)
    expect(list).not.toHaveAttribute('data-scrolling')
  })

  it('marks each area on its own', () => {
    const one = document.createElement('div')
    const two = document.createElement('div')
    document.body.append(one, two)

    one.dispatchEvent(new Event('scroll'))
    vi.advanceTimersByTime(HIDE_AFTER_MS / 2)
    two.dispatchEvent(new Event('scroll'))
    vi.advanceTimersByTime(HIDE_AFTER_MS / 2 + 1)

    expect(one).not.toHaveAttribute('data-scrolling')
    expect(two).toHaveAttribute('data-scrolling')
  })

  it('marks the page itself when the document scrolls', () => {
    document.dispatchEvent(new Event('scroll'))

    expect(document.documentElement).toHaveAttribute('data-scrolling')
    vi.advanceTimersByTime(HIDE_AFTER_MS + 1)
    expect(document.documentElement).not.toHaveAttribute('data-scrolling')
  })

  it('stops listening once removed', () => {
    stop()
    const list = document.createElement('div')
    document.body.append(list)

    list.dispatchEvent(new Event('scroll'))

    expect(list).not.toHaveAttribute('data-scrolling')
  })
})

describe('the scrollbar look', () => {
  const css = readFileSync(resolve(process.cwd(), 'src/theme/theme.css'), 'utf8')

  it('is thin and invisible until the area is scrolling', () => {
    expect(css).toMatch(/scrollbar-width:\s*thin/)
    expect(css).toMatch(/\[data-scrolling\]/)
    // at rest the thumb is transparent, so only the scrolling state draws it
    expect(css).toMatch(/scrollbar-color:\s*transparent\s+transparent/)
  })

  it('is started when the app starts', () => {
    const main = readFileSync(resolve(process.cwd(), 'src/main.tsx'), 'utf8')

    expect(main).toContain('installAutoHideScrollbars()')
  })
})
