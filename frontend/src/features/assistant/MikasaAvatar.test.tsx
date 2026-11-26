import { fireEvent, render, screen } from '@testing-library/react'
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { MIKASA_FACE, MikasaAvatar } from './MikasaAvatar'

describe('MikasaAvatar', () => {
  it('shows the local face image, cropped to a circle', () => {
    const { container } = render(<MikasaAvatar />)
    const img = container.querySelector('img') as HTMLImageElement
    expect(img).toHaveAttribute('src', MIKASA_FACE)
    expect(img).toHaveAttribute('alt', '') // decoration: the button already says Mikasa
    expect(img).toHaveClass('object-cover')
    expect(img.parentElement).toHaveClass('rounded-full', 'overflow-hidden')
  })

  it('falls back to the spark when the image is not there (a fresh clone has no local art)', () => {
    const { container } = render(<MikasaAvatar />)
    fireEvent.error(container.querySelector('img') as HTMLImageElement)
    expect(container.querySelector('img')).toBeNull()
    expect(container.querySelector('svg')).not.toBeNull()
  })

  it('the art stays out of git', () => {
    expect(readFileSync('../.gitignore', 'utf-8')).toMatch(/^frontend\/public\/local\/$/m)
    expect(screen.queryByRole('img')).toBeNull()
  })
})
