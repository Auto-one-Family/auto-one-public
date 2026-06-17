import { describe, it, expect } from 'vitest'
import {
  formatZoneAckSuccess,
  formatSubzoneAckError,
} from '@/domain/zone/ackPresentation'

describe('ackPresentation', () => {
  it('formatZoneAckSuccess adds Brückengrund line when reason_code set', () => {
    const r = formatZoneAckSuccess({
      deviceName: 'A',
      zoneName: 'Z',
      reasonCode: 'CONFIG_LANE_BUSY',
    })
    expect(r.title).toContain('A')
    expect(r.bridgeLine).toBe('Brückengrund (Zone): CONFIG_LANE_BUSY')
  })

  it('formatSubzoneAckError separates bridge from error code', () => {
    const r = formatSubzoneAckError({
      message: 'failed',
      reasonCode: 'JSON_PARSE_ERROR',
      errorCode: 'EE123',
    })
    expect(r.headline).toBe('failed')
    expect(r.bridgeLine).toBe('Brückengrund (Subzone): JSON_PARSE_ERROR')
    expect(r.errorCodeLine).toBe('Fehlercode (Subzone): EE123')
  })
})
