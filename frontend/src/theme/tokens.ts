/** The design tokens (DESIGN.md, "Colour"). theme.css repeats these as `--ht-*` CSS variables; a
 * test keeps the two in step. */
export const tokens = {
  background: '#12151b',
  surface: '#181c23',
  raised: '#1f242c',
  hairline: 'rgb(230 232 236 / 0.08)',
  hairlineStrong: 'rgb(230 232 236 / 0.14)',
  text: '#e6e8ec',
  textSecondary: '#a8aeb8',
  textMuted: '#8b929d',
  accent: '#a99ce6',
  accentHover: '#bbb0ef',
  accentInk: '#16121f',
  accentTint: 'rgb(169 156 230 / 0.12)',
  stageInquired: '#7fa8d8',
  stageApplied: '#6fc08d',
  stageInterview: '#d6b25e',
  stageCleared: '#5ec4b6',
  stageFailed: '#e2837a',
  success: '#6fc08d',
  warning: '#d6b25e',
  danger: '#e2837a',
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
