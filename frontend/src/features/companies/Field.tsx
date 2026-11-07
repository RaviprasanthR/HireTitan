import { useId } from 'react'

export const inputClass =
  'w-full rounded-md border border-muted-foreground bg-background px-3 py-1.5 text-sm'

type InputProps = {
  id: string
  'aria-describedby'?: string
  'aria-invalid'?: boolean
}

/** A labelled input with its field error wired up for screen readers. */
export function Field({
  label,
  error,
  children,
}: {
  label: string
  error?: string
  children: (props: InputProps) => React.ReactNode
}) {
  const id = useId()
  const errorId = `${id}-error`
  return (
    <div className="space-y-1">
      <label htmlFor={id} className="text-sm font-medium">
        {label}
      </label>
      {children({
        id,
        'aria-describedby': error ? errorId : undefined,
        'aria-invalid': error ? true : undefined,
      })}
      {error && (
        <p id={errorId} className="text-sm text-danger">
          {error}
        </p>
      )}
    </div>
  )
}
