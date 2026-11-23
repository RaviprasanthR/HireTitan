import { describe, expect, it } from 'vitest'
import { type ConnectionFacts, gmailSteps } from './gmailSteps'

const base: ConnectionFacts = {
  state: 'not_connected',
  credentials_set: false,
  credentials_from_environment: false,
  last_check_started_at: null,
}

function states(facts: ConnectionFacts, enabledSenders = 9) {
  return gmailSteps(facts, enabledSenders).map((s) => `${s.id}:${s.state}`)
}

describe('gmailSteps (US6 AS5)', () => {
  it('a fresh install starts at the Google client, the rest waits', () => {
    expect(states(base)).toEqual(['client:current', 'connect:waiting', 'senders:waiting', 'check:waiting'])
    expect(gmailSteps(base, 9).map((s) => s.waitsFor)).toEqual([
      undefined,
      'Google client',
      'Connect',
      'Connect',
    ])
  })

  it('a saved client moves on to Connect', () => {
    expect(states({ ...base, credentials_set: true })).toEqual([
      'client:done',
      'connect:current',
      'senders:waiting',
      'check:waiting',
    ])
  })

  it('a client from the environment counts as done', () => {
    expect(states({ ...base, credentials_from_environment: true })[0]).toBe('client:done')
  })

  it('connected: senders done when one is on, the first check is next', () => {
    const connected = { ...base, credentials_set: true, state: 'connected' as const }
    expect(states(connected)).toEqual(['client:done', 'connect:done', 'senders:done', 'check:current'])
  })

  it('connected with every sender off: the senders step is current', () => {
    const connected = { ...base, credentials_set: true, state: 'connected' as const }
    expect(states(connected, 0)).toEqual(['client:done', 'connect:done', 'senders:current', 'check:waiting'])
    expect(gmailSteps(connected, 0)[3]?.waitsFor).toBe('Senders')
  })

  it('everything done after the first check: no step is current', () => {
    const all = {
      ...base,
      credentials_set: true,
      state: 'connected' as const,
      last_check_started_at: '2026-11-22T17:54:01Z',
    }
    expect(states(all)).toEqual(['client:done', 'connect:done', 'senders:done', 'check:done'])
  })

  it('access ended: Connect is current again and says why', () => {
    const ended = {
      ...base,
      credentials_set: true,
      state: 'needs_reconnect' as const,
      last_check_started_at: '2026-11-22T17:54:01Z',
    }
    const steps = gmailSteps(ended, 9)
    expect(steps.map((s) => s.state)).toEqual(['done', 'current', 'waiting', 'waiting'])
    expect(steps[1]?.note).toMatch(/access has ended/i)
  })

  it('every step has a title and a short purpose', () => {
    for (const step of gmailSteps(base, 9)) {
      expect(step.title.length).toBeGreaterThan(3)
      expect(step.purpose.length).toBeGreaterThan(10)
    }
  })
})
