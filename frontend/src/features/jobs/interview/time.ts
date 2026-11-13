const pad = (n: number) => String(n).padStart(2, '0')

/** An instant from the server as the value of a `datetime-local` input, in the person's own time. */
export function toLocalInput(instant: string | null): string {
  if (!instant) return ''
  const day = new Date(instant)
  if (Number.isNaN(day.getTime())) return ''
  return (
    `${day.getFullYear()}-${pad(day.getMonth() + 1)}-${pad(day.getDate())}` +
    `T${pad(day.getHours())}:${pad(day.getMinutes())}`
  )
}

/** What a `datetime-local` input holds (local time, no offset) as an instant; empty means none. */
export function fromLocalInput(value: string): string | null {
  if (!value) return null
  const day = new Date(value)
  return Number.isNaN(day.getTime()) ? null : day.toISOString()
}
