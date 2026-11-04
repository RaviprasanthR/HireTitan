import { useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { ApiError, apiFetch } from '@/api/client'
import { PreferencesPage } from '@/features/preferences/PreferencesPage'

/** Step 4: preferences, ending with "Finish setup", which opens the usual app. */
export function PreferencesStep() {
  const queryClient = useQueryClient()
  const [error, setError] = useState<string | null>(null)

  async function finish() {
    setError(null)
    try {
      await apiFetch('/onboarding/complete', { method: 'POST' })
      await queryClient.invalidateQueries({ queryKey: ['onboarding'] })
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : 'Something went wrong. Please try again.')
    }
  }

  return (
    <div className="space-y-5">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold">What are you looking for?</h1>
        <p className="text-sm text-muted-small">
          Suggestions come from your profile. Add only what you want; you can change all of this
          later.
        </p>
      </div>
      <PreferencesPage embedded onSaved={finish} />
      {error && (
        <p role="alert" className="rounded-md border border-danger p-3 text-danger">
          {error}
        </p>
      )}
    </div>
  )
}
