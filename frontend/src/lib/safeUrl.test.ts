import { describe, expect, it } from 'vitest'
import { safeHttpUrl } from './safeUrl'

describe('safeHttpUrl', () => {
  it('keeps http and https links', () => {
    expect(safeHttpUrl('https://a.example/x')).toBe('https://a.example/x')
    expect(safeHttpUrl(' HTTP://a.example ')).toBe('HTTP://a.example')
  })
  it('drops everything else', () => {
    expect(safeHttpUrl('javascript:alert(1)')).toBeUndefined()
    expect(safeHttpUrl('data:text/html,x')).toBeUndefined()
    expect(safeHttpUrl(null)).toBeUndefined()
  })
})
