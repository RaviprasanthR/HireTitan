import { useMutation, useQueryClient } from '@tanstack/react-query'
import { apiFetch } from '@/api/client'
import { useStatus } from '@/api/useStatus'
import { Button } from '@/components/ui/button'
import { DeleteAllData } from './DeleteAllData'

const KEY_STATUS: Record<string, string> = {
  working: 'Found, working',
  missing: 'Missing',
  rejected: 'Rejected by the provider',
  unreachable: 'Provider could not be reached',
  out_of_credit: 'Out of credit at the provider',
  unknown: 'Not checked yet',
}

const KEY_HELP: Record<string, string> = {
  missing: 'Add OPENAI_API_KEY to .env, then restart HireTitan.',
  rejected: 'Replace OPENAI_API_KEY in .env, then restart HireTitan.',
  out_of_credit: 'Add credit with your provider, then press Check again.',
}

function KeyStatus({ status }: { status: string }) {
  const queryClient = useQueryClient()
  const recheck = useMutation({
    mutationFn: () => apiFetch('/status/ai/check', { method: 'POST' }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['status'] }),
  })
  const help = KEY_HELP[status]
  return (
    <section className="space-y-2" aria-labelledby="key-heading">
      <h2 id="key-heading" className="text-lg font-medium">
        AI key
      </h2>
      <p>{KEY_STATUS[status] ?? status}</p>
      {help && <p className="text-sm text-muted-small">{help}</p>}
      <p className="text-xs text-muted-small">The key itself is never shown here.</p>
      <Button
        type="button"
        variant="outline"
        disabled={recheck.isPending}
        onClick={() => recheck.mutate()}
      >
        Check again
      </Button>
    </section>
  )
}

/** The AI key status with Check again, and Delete all my data. Nothing else lives here. */
export function SettingsPage() {
  const status = useStatus()
  return (
    <section className="space-y-6">
      <h1 className="text-2xl font-semibold">Settings</h1>
      {status.isPending && <p>Loading…</p>}
      {status.isError && <p role="alert">Could not load settings.</p>}
      {status.data && (
        <div className="max-w-2xl space-y-8">
          <KeyStatus status={status.data.ai.status} />
          <DeleteAllData />
        </div>
      )}
    </section>
  )
}
