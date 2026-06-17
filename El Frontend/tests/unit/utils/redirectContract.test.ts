import { describe, expect, it } from 'vitest'
import { resolvePostLoginRedirect } from '@/utils/redirectContract'

describe('resolvePostLoginRedirect', () => {
  it('returns fallback for missing redirect', () => {
    expect(resolvePostLoginRedirect(undefined, '/')).toBe('/')
    expect(resolvePostLoginRedirect(null, '/hardware')).toBe('/hardware')
  })

  it('accepts plain semantic redirect paths', () => {
    expect(resolvePostLoginRedirect('/hardware', '/')).toBe('/hardware')
    expect(resolvePostLoginRedirect('/monitor/zone-a?sensor=1', '/')).toBe('/monitor/zone-a?sensor=1')
  })

  it('normalizes encoded redirect paths to semantic target', () => {
    expect(resolvePostLoginRedirect('%2Fhardware', '/')).toBe('/hardware')
    expect(resolvePostLoginRedirect('%2Fmonitor%2FZelt%2520Wohnzimmer', '/')).toBe('/monitor/Zelt Wohnzimmer')
  })

  it('rejects unsafe values and falls back', () => {
    expect(resolvePostLoginRedirect('https://evil.example/path', '/')).toBe('/')
    expect(resolvePostLoginRedirect('//evil.example/path', '/hardware')).toBe('/hardware')
    expect(resolvePostLoginRedirect('hardware', '/')).toBe('/')
  })
})
