/** Shows how much of a text limit is used once the text is close to it (FR-014). */
export function CharCounter({ length, max }: { length: number; max: number }) {
  if (length < max * 0.9) return null
  return (
    <span className="text-xs text-muted-small">
      {length.toLocaleString('en-US')} / {max.toLocaleString('en-US')}
    </span>
  )
}
