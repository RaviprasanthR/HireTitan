import { useMutation, useQueryClient } from '@tanstack/react-query'
import { AlertDialog } from 'radix-ui'
import { useState } from 'react'
import { useNavigate } from 'react-router'
import { ApiError, apiFetch } from '@/api/client'
import { Button } from '@/components/ui/button'

const WORD = 'DELETE'

/** The danger zone: wipe everything and start over from setup step 1 (FR-035). */
export function DeleteAllData() {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const [typed, setTyped] = useState('')
  const [error, setError] = useState<string | null>(null)

  const wipe = useMutation({
    mutationFn: () => apiFetch('/data/delete-all', { method: 'POST', json: { confirm: WORD } }),
    onSuccess: async () => {
      setOpen(false)
      await queryClient.invalidateQueries() // the setup gate now reads step 1
      navigate('/')
    },
    onError: (e) =>
      setError(e instanceof ApiError ? e.detail : 'Something went wrong. Please try again.'),
  })

  function change(next: boolean) {
    setOpen(next)
    setTyped('')
    setError(null)
  }

  return (
    <section
      className="ht-danger-zone space-y-2 rounded-lg p-4"
      aria-labelledby="danger-heading"
    >
      <h2 id="danger-heading" className="text-lg font-medium">
        Delete all my data
      </h2>
      <p className="text-sm text-muted-small">
        Removes your profile, preferences, resume files and AI usage log, and takes you back to the
        first setup step. Your API key in <code>.env</code> is not touched.
      </p>
      <Button variant="outline" className="ht-danger-button" onClick={() => change(true)}>
        Delete all my data
      </Button>

      <AlertDialog.Root open={open} onOpenChange={change}>
        <AlertDialog.Portal>
          <AlertDialog.Overlay className="fixed inset-0 bg-black/60" />
          <AlertDialog.Content className="fixed top-1/2 left-1/2 w-full max-w-lg -translate-x-1/2 -translate-y-1/2 space-y-4 rounded-lg bg-surface p-6">
            <AlertDialog.Title className="text-lg font-semibold">
              Delete everything?
            </AlertDialog.Title>
            <AlertDialog.Description className="text-sm text-muted-small">
              This cannot be undone. All your HireTitan data on this computer is erased.
            </AlertDialog.Description>
            <div className="space-y-1">
              <label htmlFor="confirm-delete" className="block text-sm font-medium">
                To confirm, type {WORD}
              </label>
              <input
                id="confirm-delete"
                autoComplete="off"
                value={typed}
                onChange={(e) => setTyped(e.target.value)}
                className="w-full rounded-md border border-muted-foreground bg-background px-3 py-2 text-sm"
              />
            </div>
            {error && (
              <p role="alert" className="text-sm text-danger">
                {error}
              </p>
            )}
            <div className="flex gap-3">
              <Button
                className="ht-danger-button ht-danger-solid"
                disabled={typed !== WORD || wipe.isPending}
                onClick={(event) => {
                  event.preventDefault() // stay open until the server answers
                  wipe.mutate()
                }}
              >
                Delete everything
              </Button>
              <AlertDialog.Cancel asChild>
                <Button variant="secondary">Cancel</Button>
              </AlertDialog.Cancel>
            </div>
          </AlertDialog.Content>
        </AlertDialog.Portal>
      </AlertDialog.Root>
    </section>
  )
}
