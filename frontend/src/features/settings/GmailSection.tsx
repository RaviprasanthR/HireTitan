import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertDialog } from 'radix-ui'
import { useState } from 'react'
import { useSearchParams } from 'react-router'
import { ApiError, apiFetch } from '@/api/client'
import type { components } from '@/api/schema'
import { Button } from '@/components/ui/button'
import { formatDate } from '../explore/api'
import { MailSenders } from './MailSenders'

type Connection = components['schemas']['ConnectionModel']

const GMAIL_GUIDE = 'https://github.com/RaviprasanthR/HireTitan/blob/master/docs/gmail-setup.md'
const CONNECTION_KEY = ['mail', 'connection'] as const

const REASONS: Record<string, string> = {
  denied: 'You did not allow access in Google, so nothing was connected.',
  wrong_scope:
    'Google granted more than read-only access, so HireTitan refused it and handed it back.',
  state: 'The sign-in took too long or did not start here. Please try again.',
  exchange_failed:
    'HireTitan could not finish connecting. Check the client ID and secret, then try again.',
}
const UNKNOWN_REASON = 'Connecting did not work. Please try again.'

const FIELD = 'w-full rounded-md border border-muted-foreground bg-background px-3 py-2 text-sm'

function messageOf(error: unknown): string {
  return error instanceof ApiError ? error.detail : 'Something went wrong. Please try again.'
}

/** What Google's redirect left in the address: `?gmail=connected` or `?gmail=error&reason=…`. */
function Result({ state }: { state: Connection['state'] | undefined }) {
  const [params] = useSearchParams()
  const outcome = params.get('gmail')
  // a stale address (after a reload, Back, or a later Disconnect) must not contradict the page
  if (outcome === 'connected' && state === 'connected') {
    return (
      <p role="status" aria-label="Gmail result" className="text-sm text-success">
        Gmail is connected.
      </p>
    )
  }
  if (outcome === 'error' && state !== 'connected') {
    const reason = params.get('reason') ?? ''
    // only known reasons are shown; anything else in the address is never echoed back
    const text = Object.hasOwn(REASONS, reason) ? REASONS[reason] : UNKNOWN_REASON
    return (
      <p role="alert" aria-label="Gmail result" className="text-sm text-danger">
        {text}
      </p>
    )
  }
  return null
}

const STEPS: { text: string; href: string; link: string }[] = [
  {
    text: 'Create a project (any name).',
    href: 'https://console.cloud.google.com/projectcreate',
    link: 'Create a project',
  },
  {
    text: 'Turn on the Gmail API for it.',
    href: 'https://console.cloud.google.com/apis/library/gmail.googleapis.com',
    link: 'Open the Gmail API page',
  },
  {
    text: 'Set up the consent screen: External, keep it on Testing, add your own Gmail as a test user.',
    href: 'https://console.cloud.google.com/apis/credentials/consent',
    link: 'Open the consent screen',
  },
  {
    text: 'Create an OAuth client of type Web application with the redirect address below, then download its JSON file.',
    href: 'https://console.cloud.google.com/apis/credentials',
    link: 'Open Credentials',
  },
]

type ClientFile = { clientId: string; clientSecret: string } | { problem: string }

/** The two values from the JSON file Google lets you download for an OAuth client. */
function readClientFile(text: string): ClientFile {
  let data: unknown
  try {
    data = JSON.parse(text)
  } catch {
    return { problem: 'That is not a Google client file.' }
  }
  const root = (data && typeof data === 'object' ? data : {}) as Record<string, unknown>
  if (root.installed)
    return {
      problem:
        'That is a Desktop client. Create a client of type Web application instead, with the redirect address shown here.',
    }
  const web = root.web as Record<string, unknown> | undefined
  if (typeof web?.client_id !== 'string' || typeof web?.client_secret !== 'string')
    return { problem: 'That is not a Google client file.' }
  return { clientId: web.client_id, clientSecret: web.client_secret }
}

function readText(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result ?? ''))
    reader.onerror = () => reject(reader.error)
    reader.readAsText(file)
  })
}

function CopyAddress({ address }: { address: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <span className="inline-flex items-center gap-2">
      <code>{address}</code>
      <Button
        type="button"
        variant="outline"
        size="xs"
        aria-label="Copy redirect address"
        onClick={() => {
          void navigator.clipboard?.writeText(address).then(() => setCopied(true))
        }}
      >
        Copy
      </Button>
      {copied && <span className="text-xs text-success">Copied</span>}
    </span>
  )
}

function Credentials({
  connection,
  onDone,
  onCancel,
}: {
  connection: Connection
  onDone: () => void
  onCancel?: () => void
}) {
  const queryClient = useQueryClient()
  const [clientId, setClientId] = useState('')
  const [clientSecret, setClientSecret] = useState('')
  const [error, setError] = useState<string | null>(null)
  const save = useMutation({
    mutationFn: () =>
      apiFetch<Connection>('/mail/credentials', {
        method: 'PUT',
        json: {
          client_id: clientId.trim(),
          client_secret: clientSecret.trim(),
        },
      }),
    onSuccess: (saved) => {
      queryClient.setQueryData(CONNECTION_KEY, saved)
      setClientSecret('') // the secret is never kept on the page
      onDone()
    },
    onError: (e) => setError(messageOf(e)),
  })

  async function loadFile(file: File | undefined) {
    if (!file) return
    setError(null)
    try {
      const read = readClientFile(await readText(file))
      if ('problem' in read) return setError(read.problem)
      setClientId(read.clientId)
      setClientSecret(read.clientSecret)
    } catch {
      setError('That file could not be read.')
    }
  }

  function submit(event: React.FormEvent) {
    event.preventDefault()
    setError(null)
    const values = [clientId.trim(), clientSecret.trim()]
    if (values.some((v) => v.length < 10 || v.length > 300 || /\s/.test(v))) {
      setError('Both values are 10 to 300 characters with no spaces.')
      return
    }
    save.mutate()
  }

  return (
    <form onSubmit={submit} className="space-y-3" aria-label="Google client">
      <p className="text-sm text-muted-small">
        Create your own Google client once. These steps open the right Google pages:
      </p>
      <ol aria-label="Setup steps" className="list-decimal space-y-1 pl-5 text-sm text-muted-small">
        {STEPS.map((step) => (
          <li key={step.href}>
            {step.text}{' '}
            <a href={step.href} target="_blank" rel="noreferrer" className="text-link underline">
              {step.link}
            </a>
          </li>
        ))}
      </ol>
      <p className="text-sm text-muted-small">
        Redirect address to register: <CopyAddress address={connection.redirect_uri} />
      </p>
      <div className="space-y-1">
        <label htmlFor="google-client-file" className="block text-sm font-medium">
          Load client_secret.json
        </label>
        <input
          id="google-client-file"
          type="file"
          accept=".json,application/json"
          onChange={(e) => void loadFile(e.target.files?.[0])}
          className="block text-sm"
        />
      </div>
      <div className="space-y-1">
        <label htmlFor="google-client-id" className="block text-sm font-medium">
          Client ID
        </label>
        <input
          id="google-client-id"
          autoComplete="off"
          spellCheck={false}
          value={clientId}
          onChange={(e) => setClientId(e.target.value)}
          className={FIELD}
        />
      </div>
      <div className="space-y-1">
        <label htmlFor="google-client-secret" className="block text-sm font-medium">
          Client secret
        </label>
        <input
          id="google-client-secret"
          type="password"
          autoComplete="new-password"
          value={clientSecret}
          onChange={(e) => setClientSecret(e.target.value)}
          className={FIELD}
        />
      </div>
      {error && (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}
      <div className="flex gap-3">
        <Button type="submit" disabled={save.isPending}>
          Save
        </Button>
        {onCancel && (
          <Button type="button" variant="cancel" onClick={onCancel}>
            Cancel
          </Button>
        )}
      </div>
    </form>
  )
}

function Disconnect({ onDone }: { onDone: (revoked: boolean) => void }) {
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const disconnect = useMutation({
    mutationFn: () => apiFetch<{ revoked: boolean }>('/mail/connection', { method: 'DELETE' }),
    onSuccess: async (result) => {
      onDone(result?.revoked !== false)
      setOpen(false)
      await queryClient.invalidateQueries({ queryKey: CONNECTION_KEY })
    },
    onError: (e) => setError(messageOf(e)),
  })

  return (
    <AlertDialog.Root
      open={open}
      onOpenChange={(next) => {
        setOpen(next)
        setError(null)
      }}
    >
      <AlertDialog.Trigger asChild>
        <Button type="button" variant="outline">
          Disconnect
        </Button>
      </AlertDialog.Trigger>
      <AlertDialog.Portal>
        <AlertDialog.Overlay className="fixed inset-0 bg-black/60" />
        <AlertDialog.Content className="fixed top-1/2 left-1/2 w-full max-w-lg -translate-x-1/2 -translate-y-1/2 space-y-4 rounded-lg bg-surface p-6">
          <AlertDialog.Title className="text-lg font-semibold">Disconnect Gmail?</AlertDialog.Title>
          <AlertDialog.Description className="text-sm text-muted-small">
            HireTitan hands its access back to Google and forgets which emails it has read. Jobs it
            already found stay in Explore.
          </AlertDialog.Description>
          {error && (
            <p role="alert" className="text-sm text-danger">
              {error}
            </p>
          )}
          <div className="flex gap-3">
            <Button
              type="button"
              variant="danger"
              disabled={disconnect.isPending}
              onClick={(event) => {
                event.preventDefault() // stay open until the server answers
                disconnect.mutate()
              }}
            >
              Disconnect Gmail
            </Button>
            <AlertDialog.Cancel asChild>
              <Button type="button" variant="cancel">
                Cancel
              </Button>
            </AlertDialog.Cancel>
          </div>
        </AlertDialog.Content>
      </AlertDialog.Portal>
    </AlertDialog.Root>
  )
}

function ConnectButton({ label }: { label: string }) {
  const [error, setError] = useState<string | null>(null)
  const connect = useMutation({
    mutationFn: () => apiFetch<{ authorize_url: string }>('/mail/connect', { method: 'POST' }),
    onSuccess: (started) => {
      // only ever navigate to a secure web address, whatever the server answered
      if (new URL(started.authorize_url, window.location.origin).protocol !== 'https:')
        return setError('Google sign-in could not be started. Please try again.')
      window.location.assign(started.authorize_url)
    },
    onError: (e) => setError(messageOf(e)),
  })
  return (
    <div className="space-y-2">
      <Button
        type="button"
        disabled={connect.isPending || connect.isSuccess}
        onClick={() => {
          setError(null)
          connect.mutate()
        }}
      >
        {label}
      </Button>
      {error && (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}
    </div>
  )
}

function formatTime(value: string): string {
  return new Date(value).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })
}

/** What a check reads, and when one last ran, so a person who has not checked for days knows
 *  that older alerts were not read (feature 002c, US5 AS5). */
function CheckWindow({ connection }: { connection: Connection }) {
  return (
    <div className="space-y-1 text-sm text-muted-small">
      <p>{`Each check reads job-alert emails from the last ${connection.window_hours} hours.`}</p>
      <p>
        {connection.last_check_started_at
          ? `Last check: ${formatDate(connection.last_check_started_at)}, ${formatTime(connection.last_check_started_at)}`
          : 'Not checked yet.'}
      </p>
    </div>
  )
}

/** Settings > Gmail job alerts: save the person's own Google client, connect read-only,
 *  disconnect. Nothing here reads mail (feature 002c, US1). */
export function GmailSection() {
  const connection = useQuery({
    queryKey: CONNECTION_KEY,
    queryFn: () => apiFetch<Connection>('/mail/connection'),
  })
  const [changing, setChanging] = useState(false)
  const [revokeFailed, setRevokeFailed] = useState(false)
  const data = connection.data

  return (
    <section className="space-y-3" aria-labelledby="gmail-heading">
      <h2 id="gmail-heading" className="text-lg font-medium">
        Gmail job alerts
      </h2>
      <p className="text-sm text-muted-small">
        HireTitan can only read the job-alert emails from senders you allow.
      </p>
      <p className="text-sm text-muted-small">
        It never sends, deletes or changes mail, and you can disconnect at any time.{' '}
        <a href={GMAIL_GUIDE} target="_blank" rel="noreferrer" className="text-link underline">
          Read the setup guide
        </a>
        .
      </p>
      <Result state={data?.state} />
      {revokeFailed && data?.state === 'not_connected' && (
        <p role="alert" aria-label="Disconnect result" className="text-sm text-danger">
          Gmail is disconnected here, but Google could not be reached to take the access back.
          Remove the app at myaccount.google.com/permissions to be sure.
        </p>
      )}
      {connection.isPending && <p>Loading…</p>}
      {connection.isError && <p role="alert">Could not load the Gmail connection.</p>}
      {data && data.state === 'not_connected' && (
        <div className="space-y-3">
          <p>Not connected</p>
          {data.credentials_from_environment ? (
            <p className="text-sm text-muted-small">
              The Google client ID and secret are set in the environment.
            </p>
          ) : (
            (!data.credentials_set || changing) && (
              <Credentials
                connection={data}
                onDone={() => setChanging(false)}
                onCancel={changing ? () => setChanging(false) : undefined}
              />
            )
          )}
          {data.credentials_set && (
            <div className="flex flex-wrap gap-3">
              <ConnectButton label="Connect Gmail" />
              {!data.credentials_from_environment && !changing && (
                <Button type="button" variant="outline" onClick={() => setChanging(true)}>
                  Change client ID and secret
                </Button>
              )}
            </div>
          )}
        </div>
      )}
      {data && data.state === 'connected' && (
        <div className="space-y-3">
          <p>{`Connected as ${data.address}`}</p>
          <CheckWindow connection={data} />
          <Disconnect onDone={(revoked) => setRevokeFailed(!revoked)} />
        </div>
      )}
      {data && data.state === 'needs_reconnect' && (
        <div className="space-y-3">
          <p>{`Connected as ${data.address}`}</p>
          <CheckWindow connection={data} />
          <p role="alert" className="text-sm text-danger">
            {data.last_error ?? 'Gmail access has ended. Connect again.'}
          </p>
          <div className="flex flex-wrap gap-3">
            <ConnectButton label="Reconnect Gmail" />
            <Disconnect onDone={(revoked) => setRevokeFailed(!revoked)} />
          </div>
        </div>
      )}
      <MailSenders />
    </section>
  )
}
