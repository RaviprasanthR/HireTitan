import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertDialog } from 'radix-ui'
import { useState } from 'react'
import { Link, useSearchParams } from 'react-router'
import { ApiError, apiFetch } from '@/api/client'
import type { components } from '@/api/schema'
import { Button } from '@/components/ui/button'
import { formatDate, useStartMailCheck } from '../explore/api'
import { type GmailStep, type StepId, type StepState, gmailSteps } from './gmailSteps'
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
    <span className="inline-flex max-w-full flex-wrap items-center gap-2">
      <code className="break-all">{address}</code>
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

const LOOPBACK = new Set(['localhost', '127.0.0.1', '[::1]'])

function safeSignInAddress(url: URL): boolean {
  return url.protocol === 'https:' || (url.protocol === 'http:' && LOOPBACK.has(url.hostname))
}

function ConnectButton({ label }: { label: string }) {
  const [error, setError] = useState<string | null>(null)
  const connect = useMutation({
    mutationFn: () => apiFetch<{ authorize_url: string }>('/mail/connect', { method: 'POST' }),
    onSuccess: (started) => {
      // only ever navigate to a secure web address, whatever the server answered; plain http only
      // to this computer (the scripted Google of the demo and e2e stack answers there)
      if (!safeSignInAddress(new URL(started.authorize_url, window.location.origin)))
        return setError('Google sign-in could not be started. Please try again.')
      window.location.assign(started.authorize_url)
    },
    onError: (e) => setError(messageOf(e)),
  })
  return (
    <div className="space-y-2">
      <Button
        type="button"
        disabled={connect.isPending}
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
  return new Date(value).toLocaleTimeString('en-GB', {
    hour: '2-digit',
    minute: '2-digit',
  })
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

const STEP_LABEL: Record<StepState, string> = {
  done: 'Done',
  current: 'Next',
  waiting: 'Waiting',
}

function StepMarker({ number, state }: { number: number; state: StepState }) {
  return (
    <span className={`ht-step-marker ht-step-marker-${state}`} aria-hidden="true">
      {state === 'done' ? '✓' : number}
    </span>
  )
}

/** The check step. Once a check has run it can also read the last day again (FR-013e), so jobs
 *  stored earlier get the company and place a better reading finds. */
function FirstCheck({ checkedBefore = false }: { checkedBefore?: boolean }) {
  const start = useStartMailCheck()
  const busy = start.isPending || start.isSuccess
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-2">
        <Button type="button" disabled={busy} onClick={() => start.mutate(false)}>
          Check job-alert mail
        </Button>
        {checkedBefore && (
          <Button type="button" variant="outline" disabled={busy} onClick={() => start.mutate(true)}>
            Read the last day again
          </Button>
        )}
      </div>
      {checkedBefore && (
        <p className="text-sm text-muted-small">
          Read again reads the last 24 hours of alert mail again and fixes the company and place of
          jobs it found before. With an AI key set, the AI reads each alert email&apos;s text.
        </p>
      )}
      {start.isSuccess && (
        <p role="status" className="text-sm text-success">
          Checking your mail. The jobs it finds appear in{' '}
          <Link to="/" className="text-link underline">
            Explore
          </Link>
          .
        </p>
      )}
      {start.isError && (
        <p role="alert" className="text-sm text-danger">
          {messageOf(start.error)}
        </p>
      )}
    </div>
  )
}

/** Settings > Gmail job alerts: the set-up as ordered steps (Google client, Connect, Senders,
 *  First check), each done, next or waiting from the app's real state (002c US1, US6). A done
 *  step keeps a one-line summary and its main action; it can be opened again. */
export function GmailSection() {
  const connection = useQuery({
    queryKey: CONNECTION_KEY,
    queryFn: () => apiFetch<Connection>('/mail/connection'),
  })
  const senders = useQuery({
    queryKey: ['mail', 'senders'],
    queryFn: () => apiFetch<{ items: { enabled: boolean }[] }>('/mail/senders'),
  })
  // a step the person opened stays open only while the steps stay as they were: after Connect,
  // Disconnect or a saved client, the page opens the new current step again
  const [opened, setOpenedState] = useState<{ id: StepId; key: string } | null>(null)
  const [revokeFailed, setRevokeFailed] = useState(false)
  const data = connection.data
  // an unknown sender list (still loading, or not answered) never blocks the next step
  const enabled = senders.data ? senders.data.items.filter((s) => s.enabled).length : 1
  const steps = data ? gmailSteps(data, enabled) : []
  const current = steps.find((s) => s.state === 'current')?.id
  const stateKey = steps.map((s) => s.state).join(',')
  const open = opened && opened.key === stateKey ? opened.id : current
  const setOpened = (id: StepId | null) => setOpenedState(id ? { id, key: stateKey } : null)
  const toggle = (id: StepId) => setOpened(open === id ? null : id)

  function summary(step: GmailStep, conn: Connection) {
    switch (step.id) {
      case 'client':
        if (conn.credentials_from_environment)
          return 'The Google client ID and secret are set in the environment.'
        return step.state === 'done' ? 'Client ID and secret saved.' : null
      case 'connect':
        if (conn.state === 'needs_reconnect') return `Was connected as ${conn.address}.`
        return conn.state === 'not_connected' ? 'Not connected' : `Connected as ${conn.address}`
      case 'senders':
        return senders.data
          ? `${enabled} of ${senders.data.items.length} senders on, plus each site's own domain.`
          : null
      case 'check':
        return conn.state === 'not_connected' ? null : <CheckWindow connection={conn} />
    }
  }

  function body(step: GmailStep, conn: Connection) {
    switch (step.id) {
      case 'client':
        return conn.credentials_from_environment ? null : (
          <Credentials
            connection={conn}
            onDone={() => setOpened(null)}
            onCancel={conn.credentials_set ? () => setOpened(null) : undefined}
          />
        )
      case 'connect':
        if (conn.state === 'connected') return null
        return (
          <div className="space-y-3">
            {conn.state === 'needs_reconnect' && (
              <p role="alert" className="text-sm text-danger">
                {conn.last_error ?? step.note ?? 'Gmail access has ended. Connect again.'}
              </p>
            )}
            {conn.credentials_set || conn.credentials_from_environment ? (
              <ConnectButton
                label={conn.state === 'needs_reconnect' ? 'Reconnect Gmail' : 'Connect Gmail'}
              />
            ) : (
              <p className="text-sm text-muted-small">Save your Google client first (step 1).</p>
            )}
          </div>
        )
      case 'senders':
        return <MailSenders heading={false} />
      case 'check':
        return conn.state === 'connected' ? <FirstCheck /> : null
    }
  }

  function actions(step: GmailStep, conn: Connection) {
    // the client can be changed whenever Gmail is not connected (a rotated secret is a common
    // reason a reconnect fails)
    if (step.id === 'client' && step.state === 'done' && conn.state !== 'connected') {
      if (conn.credentials_from_environment || open === 'client') return null
      return (
        <Button type="button" variant="outline" size="xs" onClick={() => setOpened('client')}>
          Change client ID and secret
        </Button>
      )
    }
    if (step.id === 'connect' && conn.state !== 'not_connected')
      return <Disconnect onDone={(revoked) => setRevokeFailed(!revoked)} />
    if (step.id === 'senders' && step.state === 'done')
      return (
        <Button
          type="button"
          variant="outline"
          size="xs"
          aria-expanded={open === 'senders'}
          onClick={() => toggle('senders')}
        >
          {open === 'senders' ? 'Hide senders' : 'Show senders'}
        </Button>
      )
    if (step.id === 'check' && step.state === 'done') return <FirstCheck checkedBefore />
    return null
  }

  return (
    <section
      id="gmail-settings"
      aria-labelledby="gmail-heading"
      className="ht-detail-card ht-settings-gmail space-y-4 scroll-mt-6"
    >
      <header className="space-y-1">
        <h2 id="gmail-heading" className="text-lg font-semibold">
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
      </header>
      <Result state={data?.state} />
      {revokeFailed && data?.state === 'not_connected' && (
        <p role="alert" aria-label="Disconnect result" className="text-sm text-danger">
          Gmail is disconnected here, but Google could not be reached to take the access back.
          Remove the app at myaccount.google.com/permissions to be sure.
        </p>
      )}
      {connection.isPending && <p>Loading…</p>}
      {connection.isError && <p role="alert">Could not load the Gmail connection.</p>}
      {data && (
        <ol aria-label="Gmail set-up steps" className="ht-steps">
          {steps.map((step, index) => {
            const isOpen = open === step.id
            const line = summary(step, data)
            const buttons = actions(step, data)
            return (
              <li
                key={step.id}
                className={`ht-step ht-step-${step.state}`}
                aria-current={step.state === 'current' ? 'step' : undefined}
              >
                <StepMarker number={index + 1} state={step.state} />
                <div className="min-w-0 flex-1 space-y-2">
                  <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                    <h3 className="font-medium">{step.title}</h3>
                    <span className="text-xs text-muted-small">
                      {step.state === 'waiting' && step.waitsFor
                        ? `Waits for ${step.waitsFor}`
                        : STEP_LABEL[step.state]}
                    </span>
                  </div>
                  {(step.state !== 'done' || isOpen) && (
                    <p className="text-sm text-muted-small">{step.purpose}</p>
                  )}
                  {line && <div className="text-sm">{line}</div>}
                  {isOpen && body(step, data)}
                  {buttons && <div className="flex flex-wrap gap-3">{buttons}</div>}
                </div>
              </li>
            )
          })}
        </ol>
      )}
    </section>
  )
}
