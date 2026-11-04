import { render, screen, within } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { describe, expect, it } from 'vitest'
import { routes } from './routes'

function renderAt(path: string) {
  const router = createMemoryRouter(routes, { initialEntries: [path] })
  return render(<RouterProvider router={router} />)
}

describe('Shell', () => {
  it('FR027_sidebar_has_five_sections', () => {
    renderAt('/')
    const nav = screen.getByRole('navigation', { name: 'Main' })
    const links = within(nav).getAllByRole('link')
    expect(links.map((link) => link.textContent)).toEqual([
      'Home',
      'Profile',
      'Preferences',
      'Review',
      'Settings',
    ])
  })

  it('marks_the_current_section', () => {
    renderAt('/profile')
    expect(screen.getByRole('link', { name: 'Profile' })).toHaveAttribute('aria-current', 'page')
    expect(screen.getByRole('link', { name: 'Home' })).not.toHaveAttribute('aria-current')
  })

  it.each([
    ['/', 'Home'],
    ['/profile', 'Profile'],
    ['/profile/review/abc', 'Review your profile'],
    ['/profile/versions/v1', 'Profile version'],
    ['/preferences', 'Preferences'],
    ['/review', 'Review'],
    ['/settings', 'Settings'],
  ])('route_%s_renders_%s', (path, heading) => {
    renderAt(path)
    expect(screen.getByRole('heading', { level: 1, name: heading })).toBeInTheDocument()
  })

  it('has_a_banner_slot_above_the_page', () => {
    renderAt('/')
    expect(screen.getByTestId('banner-slot')).toBeInTheDocument()
  })

  it('unknown_path_shows_not_found_inside_the_shell', () => {
    renderAt('/nope')
    expect(screen.getByRole('heading', { level: 1, name: 'Page not found' })).toBeInTheDocument()
    expect(screen.getByRole('navigation', { name: 'Main' })).toBeInTheDocument()
  })
})
