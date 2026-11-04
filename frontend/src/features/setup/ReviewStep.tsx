import { useQueryClient } from '@tanstack/react-query'
import { ReviewEditor } from '@/features/profile/ReviewEditor'
import type { Onboarding } from './useOnboarding'

/** Step 3: check the profile (extracted or typed in) and confirm it. */
export function ReviewStep({
  onboarding,
  debounceMs,
}: {
  onboarding: Onboarding
  debounceMs?: number
}) {
  const queryClient = useQueryClient()
  // Confirming or discarding changes what step the saved data points to.
  const refreshStep = async () => {
    await queryClient.invalidateQueries({ queryKey: ['onboarding'] })
    await queryClient.invalidateQueries({ queryKey: ['profile'] })
  }

  return (
    <div className="space-y-5">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold">Check your profile</h1>
        <p className="text-sm text-muted-small">
          Edit anything that is wrong or missing. Nothing is used until you confirm.
        </p>
      </div>
      {onboarding.open_review_id ? (
        <ReviewEditor
          reviewId={onboarding.open_review_id}
          debounceMs={debounceMs}
          embedded
          defaultName={onboarding.display_name ?? undefined}
          onFinished={() => void refreshStep()}
        />
      ) : (
        <p>Loading your review…</p>
      )}
    </div>
  )
}
