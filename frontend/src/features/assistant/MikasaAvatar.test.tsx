import { fireEvent, render, screen } from '@testing-library/react'
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { MIKASA_FACE, MikasaAvatar } from './MikasaAvatar'

describe('MikasaAvatar', () => {
  it('shows the cut-out face as it is, with no circle around it', () => {
    const { container } = render(<MikasaAvatar />)
    const img = container.querySelector('img') as HTMLImageElement
    expect(img).toHaveAttribute('src', MIKASA_FACE)
    expect(MIKASA_FACE).toMatch(/\.png$/) // transparent around the face
    expect(img).toHaveAttribute('alt', '') // decoration: the button already says Mikasa
    expect(img).toHaveClass('object-contain')
    expect(img.parentElement?.className).not.toMatch(/rounded-full|overflow-hidden|bg-primary/)
  })

  it('falls back to the spark when the image is not there (a fresh clone has no local art)', () => {
    const { container } = render(<MikasaAvatar />)
    fireEvent.error(container.querySelector('img') as HTMLImageElement)
    expect(container.querySelector('img')).toBeNull()
    expect(container.querySelector('svg')).not.toBeNull()
    // the spark keeps its round accent disc
    expect((container.firstChild as HTMLElement).className).toMatch(/rounded-full/)
  })

  it('the art stays out of git', () => {
    expect(readFileSync('../.gitignore', 'utf-8')).toMatch(/^frontend\/public\/local\/$/m)
    expect(screen.queryByRole('img')).toBeNull()
  })
})
