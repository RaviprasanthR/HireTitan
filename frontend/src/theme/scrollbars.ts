/** How long a scrollbar stays visible after the last scroll movement. */
export const HIDE_AFTER_MS = 900

/**
 * Scrollbars show only while an area is scrolling.
 *
 * CSS cannot tell that something is scrolling, so this marks the scrolled element with
 * `data-scrolling` and clears the mark shortly after the last movement; `theme.css` draws the
 * scrollbar thumb only for a marked element. `scroll` events do not bubble, so one listener on the
 * document captures them for every scrollable area, including the page itself. Returns a function
 * that removes the listener.
 */
export function installAutoHideScrollbars(): () => void {
  const timers = new WeakMap<Element, ReturnType<typeof setTimeout>>()

  const onScroll = (event: Event) => {
    const target = event.target
    const area =
      target instanceof Element
        ? target
        : target === document
          ? document.documentElement
          : null
    if (!area) return
    area.setAttribute('data-scrolling', '')
    clearTimeout(timers.get(area))
    timers.set(
      area,
      setTimeout(() => area.removeAttribute('data-scrolling'), HIDE_AFTER_MS),
    )
  }

  document.addEventListener('scroll', onScroll, { capture: true, passive: true })
  return () => document.removeEventListener('scroll', onScroll, { capture: true })
}
