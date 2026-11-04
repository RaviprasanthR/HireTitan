import { useQueryClient } from '@tanstack/react-query'
import { type FormEvent, useState } from 'react'
import { ApiError, apiFetch } from '@/api/client'
import { Button } from '@/components/ui/button'

const input = 'w-full rounded-md border border-muted-foreground bg-background px-3 py-2 text-sm'

/** Step 1: the user's name. Also used to change it from step 2 (`initialName`, `onSaved`). */
export function NameStep({
  initialName = '',
  onSaved,
}: {
  initialName?: string
  onSaved?: () => void
}) {
  const queryClient = useQueryClient()
  const [name, setName] = useState(initialName)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (name.trim() === '') {
      setError('Enter your name to continue.')
      return
    }
    setError(null)
    setBusy(true)
    try {
      await apiFetch('/onboarding/name', {
        method: 'PUT',
        json: { display_name: name.trim() },
      })
      await queryClient.invalidateQueries({ queryKey: ['onboarding'] })
      onSaved?.()
    } catch (e) {
      setError(
        e instanceof ApiError
          ? (e.fieldError('display_name') ?? e.detail)
          : 'Something went wrong. Please try again.',
      )
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={submit} className="space-y-4" noValidate>
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold">Welcome to HireTitan</h1>
        <p className="text-sm text-muted-small">
          Your own job-search assistant. Everything stays on this computer.
        </p>
      </div>
      <div className="space-y-1">
        <label htmlFor="display-name" className="block text-sm font-medium">
          Your name
        </label>
        <input
          id="display-name"
          className={input}
          value={name}
          autoComplete="name"
          autoFocus
          onChange={(e) => setName(e.target.value)}
          aria-invalid={error ? true : undefined}
        />
        <p className="text-xs text-muted-small">What should we call you?</p>
        {error && (
          <p role="alert" className="text-sm text-danger">
            {error}
          </p>
        )}
      </div>
      <Button type="submit" disabled={busy}>
        Continue
      </Button>
    </form>
  )
}
