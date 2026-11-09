import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { type FormEvent, useState } from 'react'
import { ApiError, apiFetch } from '@/api/client'
import type { components } from '@/api/schema'
import { Button } from '@/components/ui/button'
import { DeleteAllData } from './DeleteAllData'

type SettingsOut = components['schemas']['SettingsOut']

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

const input = 'w-full rounded-md border border-muted-foreground bg-background px-3 py-2 text-sm'
const usd = (value: number) => `$${value.toFixed(2)}`

function validCap(text: string): boolean {
  const value = Number(text)
  return text.trim() !== '' && Number.isFinite(value) && value >= 0 && value <= 10_000
}

function SettingsForm({ data }: { data: SettingsOut }) {
  const queryClient = useQueryClient()
  const [cap, setCap] = useState(String(Number(data.budget_cap_usd)))
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)

  const save = useMutation({
    mutationFn: (value: string) =>
      apiFetch('/settings', { method: 'PUT', json: { budget_cap_usd: value } }),
    onSuccess: async () => {
      setSaved(true)
      await queryClient.invalidateQueries({ queryKey: ['settings'] })
      await queryClient.invalidateQueries({ queryKey: ['status'] })
    },
    onError: (e) => {
      setSaved(false)
      setError(
        e instanceof ApiError
          ? (e.fieldError('budget_cap_usd') ?? e.detail)
          : 'Something went wrong. Please try again.',
      )
    },
  })
  const recheck = useMutation({
    mutationFn: () => apiFetch('/status/ai/check', { method: 'POST' }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['status'] }),
  })

  function submit(event: FormEvent) {
    event.preventDefault()
    setSaved(false)
    if (!validCap(cap)) {
      setError('Enter an amount between 0 and 10000 USD.')
      return
    }
    setError(null)
    save.mutate(cap.trim())
  }

  const spent = Number(data.spent_this_month_usd)
  const limit = Number(data.budget_cap_usd)
  const percent = limit > 0 ? Math.min(100, Math.round((spent / limit) * 100)) : 100
  const help = KEY_HELP[data.key_status]

  return (
    <div className="max-w-2xl space-y-8">
      <section className="space-y-2" aria-labelledby="key-heading">
        <h2 id="key-heading" className="text-lg font-medium">
          AI key
        </h2>
        <p>{KEY_STATUS[data.key_status] ?? data.key_status}</p>
        {help && <p className="text-sm text-muted-small">{help}</p>}
        <p className="text-xs text-muted-small">The key itself is never shown here.</p>
        <Button type="button" variant="outline" disabled={recheck.isPending} onClick={() => recheck.mutate()}>
          Check again
        </Button>
      </section>

      <section className="space-y-3" aria-labelledby="budget-heading">
        <h2 id="budget-heading" className="text-lg font-medium">
          AI budget
        </h2>
        {spent >= limit && (
          <p role="status" aria-label="Budget" className="rounded-md border border-warning p-3 text-sm">
            You have reached this month&apos;s AI budget, so AI tasks are paused. Raise the cap to
            continue; paused work resumes by itself.
          </p>
        )}
        <p className="text-sm">
          {usd(spent)} of {usd(limit)} spent this month
        </p>
        <div
          role="progressbar"
          aria-label="Spent this month"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={percent}
          className="h-2 w-full overflow-hidden rounded-full bg-muted"
        >
          <div className="h-full bg-primary" style={{ width: `${percent}%` }} />
        </div>
        <form onSubmit={submit} className="space-y-2" noValidate>
          <label htmlFor="budget-cap" className="block text-sm font-medium">
            Monthly budget cap (USD)
          </label>
          <div className="flex gap-2">
            <input
              id="budget-cap"
              inputMode="decimal"
              className={`${input} max-w-40`}
              value={cap}
              onChange={(e) => {
                setCap(e.target.value)
                setSaved(false)
              }}
            />
            <Button type="submit" disabled={save.isPending}>
              Save cap
            </Button>
          </div>
          {error && (
            <p role="alert" className="text-sm text-danger">
              {error}
            </p>
          )}
          {saved && <p className="text-sm text-success">Saved</p>}
        </form>
      </section>

      <section className="space-y-2" aria-labelledby="models-heading">
        <h2 id="models-heading" className="text-lg font-medium">
          Models
        </h2>
        <p className="text-sm text-muted-small">Fixed defaults in this version.</p>
        <table aria-label="Models by tier" className="w-full text-sm">
          <thead>
            <tr className="text-left">
              <th className="py-1">Tier</th>
              <th className="py-1">Provider</th>
              <th className="py-1">Model</th>
            </tr>
          </thead>
          <tbody>
            {data.tiers.map((t) => (
              <tr key={t.tier}>
                <td className="py-1">{t.tier}</td>
                <td className="py-1">{t.provider}</td>
                <td className="py-1">{t.model}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <DeleteAllData />
    </div>
  )
}

export function SettingsPage() {
  const query = useQuery({
    queryKey: ['settings'],
    queryFn: () => apiFetch<SettingsOut>('/settings'),
    refetchOnWindowFocus: false,
  })
  return (
    <section className="space-y-6">
      <h1 className="text-2xl font-semibold">Settings</h1>
      {query.isPending && <p>Loading…</p>}
      {query.isError && <p role="alert">Could not load settings.</p>}
      {query.data && <SettingsForm data={query.data} />}
    </section>
  )
}
