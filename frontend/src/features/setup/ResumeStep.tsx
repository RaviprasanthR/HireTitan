import { useQueryClient } from '@tanstack/react-query'
import { Dialog } from 'radix-ui'
import { useState } from 'react'
import { ApiError, apiFetch } from '@/api/client'
import { useStatus } from '@/api/useStatus'
import { Button } from '@/components/ui/button'
import { ProfilePage } from '@/features/profile/ProfilePage'
import type { Onboarding } from './useOnboarding'

/** Step 2: add the resume (upload) or choose to type the profile in. */
export function ResumeStep({ onboarding, onBack }: { onboarding: Onboarding; onBack: () => void }) {
  const queryClient = useQueryClient()
  const aiStatus = useStatus().data?.ai?.status
  const keyProblem = aiStatus === 'missing' || aiStatus === 'rejected'
  const [confirming, setConfirming] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const activeRun = onboarding.active_run_id

  async function typeItIn(cancelActive: boolean) {
    setError(null)
    setBusy(true)
    try {
      await apiFetch(`/profile/reviews/manual${cancelActive ? '?cancel_active_run=true' : ''}`, {
        method: 'POST',
      })
      setConfirming(false)
      await queryClient.invalidateQueries({ queryKey: ['onboarding'] })
    } catch (e) {
      setConfirming(false)
      setError(e instanceof ApiError ? e.detail : 'Something went wrong. Please try again.')
    } finally {
      setBusy(false)
    }
  }

  function chooseTypeItIn() {
    if (activeRun) setConfirming(true)
    else void typeItIn(false)
  }

  return (
    <div className="space-y-5">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold">
          Hi {onboarding.display_name ?? 'there'}, add your resume
        </h1>
        <p className="text-sm text-muted-small">
          We read it and fill in your profile. You check everything next, and nothing is saved as
          your profile until you confirm it.
        </p>
      </div>

      {keyProblem && (
        <p role="status" className="rounded-md border border-warning p-3 text-sm">
          Reading a resume needs a working AI key. Add OPENAI_API_KEY to .env and restart, or type
          your profile in yourself.
        </p>
      )}

      <ProfilePage embedded resumeRunId={activeRun} onTypeItIn={chooseTypeItIn} />

      {error && (
        <p role="alert" className="rounded-md border border-danger p-3 text-danger">
          {error}
        </p>
      )}

      <div className="flex flex-wrap items-center gap-3 border-t border-divider pt-4">
        <Button type="button" variant="outline" onClick={onBack}>
          Back
        </Button>
        <Button type="button" variant="secondary" disabled={busy} onClick={chooseTypeItIn}>
          Type it in myself
        </Button>
      </div>

      <Dialog.Root open={confirming} onOpenChange={setConfirming}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 bg-black/60" />
          <Dialog.Content className="bg-surface fixed top-1/2 left-1/2 w-full max-w-md -translate-x-1/2 -translate-y-1/2 space-y-4 rounded-lg p-6">
            <Dialog.Title className="text-lg font-semibold">
              Stop reading the resume and type your profile in yourself?
            </Dialog.Title>
            <Dialog.Description className="text-sm text-muted-small">
              The resume you added stays saved. HireTitan just stops reading it.
            </Dialog.Description>
            <div className="flex flex-wrap gap-3">
              <Button type="button" disabled={busy} onClick={() => void typeItIn(true)}>
                Yes, stop and type it in
              </Button>
              <Button type="button" variant="outline" onClick={() => setConfirming(false)}>
                Keep reading
              </Button>
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </div>
  )
}
