/** The colour palette (architecture §10). theme.css repeats these as CSS variables. */
export const tokens = {
  background: '#131a24',
  surface: '#18202b',
  divider: '#2a3444',
  slate: '#3a465a',
  muted: '#8c97a9',
  mutedSmall: '#8c97a9',
  primary: '#243044',
  onPrimary: '#f0a35e',
  accent: '#f0a35e',
  heading: '#f1f3f7',
  text: '#e3e7ee',
  success: '#3fb950',
  warning: '#d29922',
  danger: '#f85149',
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
