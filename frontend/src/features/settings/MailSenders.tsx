import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { ApiError, apiFetch } from '@/api/client'
import type { components } from '@/api/schema'
import { Button } from '@/components/ui/button'

type Sender = components['schemas']['SenderOut']

const KEY = ['mail', 'senders'] as const
const SITE_NAMES: Record<string, string> = {
  linkedin: 'LinkedIn',
  naukri: 'Naukri',
  indeed: 'Indeed',
  foundit: 'Foundit',
  instahyre: 'Instahyre',
  cutshort: 'Cutshort',
}
const FIELD = 'w-full rounded-md border border-muted-foreground bg-background px-3 py-2 text-sm'
// the server's plain-address rule (lower-cased first); the server stays the judge
const ADDRESS = /^[a-z0-9._%][a-z0-9._%+-]*@[a-z0-9-]+(\.[a-z0-9-]+)+$/

function messageOf(error: unknown): string {
  if (error instanceof ApiError) return error.detail
  return error instanceof Error ? error.message : 'Something went wrong. Please try again.'
}

function bySite(senders: Sender[]): [string, Sender[]][] {
  const groups = new Map<string, Sender[]>()
  for (const sender of senders.filter((s) => s.built_in)) {
    groups.set(sender.site, [...(groups.get(sender.site) ?? []), sender])
  }
  return [...groups.entries()]
}

/** Settings > Gmail job alerts > Senders: which addresses count as job alerts (feature 002c, US4).
 *  A site's switch covers all its addresses; the person's own addresses can be added and removed. */
export function MailSenders({ heading = true }: { heading?: boolean } = {}) {
  const queryClient = useQueryClient()
  const senders = useQuery({
    queryKey: KEY,
    queryFn: () => apiFetch<{ items: Sender[] }>('/mail/senders'),
  })
  const [address, setAddress] = useState('')
  const [error, setError] = useState<string | null>(null)
  const refresh = () => queryClient.invalidateQueries({ queryKey: KEY })

  const switchSite = useMutation({
    mutationFn: async ({ rows, enabled }: { rows: Sender[]; enabled: boolean }) => {
      // every address is tried even if one fails, and the list is read again either way, so a
      // half-changed site is shown as it is and never hidden
      const results = await Promise.allSettled(
        rows.map((row) =>
          apiFetch(`/mail/senders/${row.id}`, { method: 'PATCH', json: { enabled } }),
        ),
      )
      const failed = results.filter((r) => r.status === 'rejected')
      if (failed.length > 0)
        throw new Error(
          `${failed.length} of ${rows.length} addresses could not be changed. Try again.`,
        )
    },
    onSettled: () => refresh(),
    onError: (e) => setError(messageOf(e)),
  })
  const add = useMutation({
    mutationFn: (value: string) =>
      apiFetch<Sender>('/mail/senders', { method: 'POST', json: { address: value } }),
    onSuccess: () => {
      setAddress('')
      return refresh()
    },
    onError: (e) => setError(messageOf(e)),
  })
  const remove = useMutation({
    mutationFn: (id: string) => apiFetch(`/mail/senders/${id}`, { method: 'DELETE' }),
    onSettled: () => refresh(),
    onError: (e) => setError(messageOf(e)),
  })

  function submit(event: React.FormEvent) {
    event.preventDefault()
    if (add.isPending) return
    setError(null)
    const value = address.trim()
    if (value.length < 3 || value.length > 320 || !ADDRESS.test(value.toLowerCase())) {
      setError('Type a plain email address, such as digest@board.example.')
      return
    }
    add.mutate(value)
  }

  const items = senders.data?.items ?? []
  const own = items.filter((s) => !s.built_in)

  return (
    <div className="space-y-3">
      {heading && <h3 className="font-medium">Senders HireTitan reads</h3>}
      <p className="text-sm text-muted-small">
        Mail from these addresses, and from each site's own domain (for example naukri.com), is
        looked at; only job alerts in it are kept and the rest is dropped. Switch a site off to
        stop reading it.
      </p>
      {error && (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}
      {senders.isPending && <p className="text-sm">Loading…</p>}
      {senders.isError && <p className="text-sm">Could not load the sender list.</p>}
      {bySite(items).map(([site, rows]) => {
        const name = SITE_NAMES[site] ?? site
        const on = rows.every((r) => r.enabled)
        const partly = !on && rows.some((r) => r.enabled)
        return (
          <fieldset key={site} className="space-y-1 rounded-md bg-surface px-3 py-2">
            <legend className="px-1 text-sm font-medium">{name}</legend>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                role="switch"
                aria-label={`Read ${name} alerts`}
                checked={on}
                disabled={switchSite.isPending}
                aria-checked={partly ? 'mixed' : on}
                onChange={() => {
                  setError(null)
                  switchSite.mutate({ rows, enabled: !on })
                }}
              />
              {on ? 'On' : partly ? 'Partly on' : 'Off'}
            </label>
            <ul className="space-y-0.5 text-sm text-muted-small">
              {rows.map((row) => (
                <li key={row.id}>{row.address}</li>
              ))}
            </ul>
          </fieldset>
        )
      })}
      {own.length > 0 && (
        <fieldset className="space-y-1 rounded-md bg-surface px-3 py-2">
          <legend className="px-1 text-sm font-medium">Senders you added</legend>
          <ul className="space-y-1 text-sm">
            {own.map((row) => (
              <li key={row.id} className="flex flex-wrap items-center justify-between gap-3">
                <span>{row.address}</span>
                <Button
                  type="button"
                  variant="outline"
                  size="xs"
                  aria-label={`Remove ${row.address}`}
                  disabled={remove.isPending}
                  onClick={() => {
                    setError(null)
                    remove.mutate(row.id)
                  }}
                >
                  Remove
                </Button>
              </li>
            ))}
          </ul>
        </fieldset>
      )}
      <form onSubmit={submit} className="space-y-2" aria-label="Add a sender">
        <label htmlFor="mail-sender-address" className="block text-sm font-medium">
          Sender address
        </label>
        <div className="flex gap-3">
          <input
            id="mail-sender-address"
            aria-invalid={error !== null}
            type="text"
            autoComplete="off"
            spellCheck={false}
            value={address}
            onChange={(e) => setAddress(e.target.value)}
            className={FIELD}
          />
          <Button type="submit" disabled={add.isPending}>
            Add sender
          </Button>
        </div>
        <p className="text-xs text-muted-small">
          Add the address a job board or digest sends from.
        </p>
      </form>
    </div>
  )
}
