/** The colour palette (architecture §10). theme.css repeats these as CSS variables. */
export const tokens = {
  background: '#261f32',
  surface: '#41394f',
  divider: '#625d73',
  muted: '#86819e',
  mutedSmall: '#938eab',
  primary: '#594ba0',
  accent: '#a99ce6',
  text: '#fbfafb',
  success: '#5fc9a0',
  warning: '#e0b25a',
  danger: '#e07a8a',
} as const

function channel(value: number): number {
  const c = value / 255
  return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4
}

function luminance(hex: string): number {
  const n = Number.parseInt(hex.replace('#', ''), 16)
  const r = channel((n >> 16) & 255)
  const g = channel((n >> 8) & 255)
  const b = channel(n & 255)
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}

/** WCAG 2.x contrast ratio between two `#rrggbb` colours (1 to 21). */
export function contrastRatio(a: string, b: string): number {
  const la = luminance(a)
  const lb = luminance(b)
  return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05)
}
