/** The Gmail set-up as ordered steps, worked out from the app's real state (002c US6, FR-031).
 *  Pure: the page shows what this says. The first step that is not done is the current one. */

export type StepId = 'client' | 'connect' | 'senders' | 'check'
export type StepState = 'done' | 'current' | 'waiting'

export interface ConnectionFacts {
  state: 'not_connected' | 'connected' | 'needs_reconnect'
  credentials_set: boolean
  credentials_from_environment: boolean
  last_check_started_at: string | null
}

export interface GmailStep {
  id: StepId
  title: string
  purpose: string
  state: StepState
  /** For a waiting step: the title of the step it waits for. */
  waitsFor?: string
  /** Something the person should know about this step right now. */
  note?: string
}

const TITLES: Record<StepId, { title: string; purpose: string }> = {
  client: {
    title: 'Google client',
    purpose: 'Your own Google client ID and secret, so HireTitan can ask Gmail for read-only access.',
  },
  connect: {
    title: 'Connect',
    purpose: 'Sign in with Google and allow read-only access to your mail.',
  },
  senders: {
    title: 'Senders',
    purpose: 'Which job sites and addresses count as job alerts.',
  },
  check: {
    title: 'First check',
    purpose: 'Read the last 24 hours of job-alert mail and see the jobs in Explore.',
  },
}

export function gmailSteps(facts: ConnectionFacts, enabledSenders: number): GmailStep[] {
  const done: Record<StepId, boolean> = {
    client: facts.credentials_set || facts.credentials_from_environment,
    connect: facts.state === 'connected',
    senders: facts.state === 'connected' && enabledSenders > 0,
    check: facts.state === 'connected' && facts.last_check_started_at !== null,
  }
  const order: StepId[] = ['client', 'connect', 'senders', 'check']
  // what each step needs first ("check" needs a connection and at least one sender)
  const needs: Record<StepId, StepId[]> = {
    client: [],
    connect: ['client'],
    senders: ['connect'],
    check: ['connect', 'senders'],
  }
  const current = order.find((id) => !done[id] && needs[id].every((n) => done[n]))
  return order.map((id) => {
    const state: StepState = done[id] ? 'done' : id === current ? 'current' : 'waiting'
    const missing = needs[id].find((n) => !done[n])
    const step: GmailStep = { id, ...TITLES[id], state }
    if (state === 'waiting' && missing) step.waitsFor = TITLES[missing].title
    if (id === 'connect' && facts.state === 'needs_reconnect')
      step.note = 'Gmail access has ended (Google ends it after 7 days in testing mode). Connect again.'
    return step
  })
}
