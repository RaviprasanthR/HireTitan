import { errorOf } from './errors'

/** The result line under a form: an error that has no field of its own, or the saved note. */
export function Message({
  error,
  saved,
  fields,
}: {
  error: unknown
  saved: string | null
  /** The fields this form shows an error for; an error about any other field is shown here. */
  fields: string[]
}) {
  const api = errorOf(error)
  // field errors are shown on their fields; anything else is shown here
  if (error && (!api || !api.fieldErrors.some((e) => fields.includes(e.field)))) {
    return (
      <p role="alert" className="text-sm text-danger">
        {error instanceof Error ? error.message : 'Could not save.'}
      </p>
    )
  }
  return saved ? (
    <p role="status" className="text-sm text-muted-small">
      {saved}
    </p>
  ) : null
}
