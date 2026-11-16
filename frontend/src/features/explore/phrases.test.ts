import { describe, expect, it } from 'vitest'
import { SEARCH_PHRASES, nextPhrase } from './phrases'

describe('search phrases', () => {
  it('never repeats the phrase before and always picks one from the list', () => {
    for (const phrase of SEARCH_PHRASES) {
      for (const r of [0, 0.25, 0.5, 0.999]) {
        const next = nextPhrase(phrase, () => r)
        expect(next).not.toBe(phrase)
        expect(SEARCH_PHRASES).toContain(next)
      }
    }
  })

  it('says nothing about cost, batches or counts', () => {
    for (const phrase of SEARCH_PHRASES) {
      expect(phrase).not.toMatch(/cost|price|token|batch|\d/i)
    }
  })
})
