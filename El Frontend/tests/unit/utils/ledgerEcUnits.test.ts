import { describe, expect, it } from 'vitest'
import {
  ledgerMsCmToUsCm,
  optionalUsCmToLedgerMsCm,
  usCmToLedgerMsCm,
  US_PER_MS,
} from '@/utils/ledgerEcUnits'

describe('ledgerEcUnits', () => {
  it('should use the same 1000 factor as server ledger_ec_units', () => {
    expect(US_PER_MS).toBe(1000)
  })

  it('should convert µS/cm to ledger mS/cm (write boundary)', () => {
    expect(usCmToLedgerMsCm(2000)).toBeCloseTo(2.0)
    expect(usCmToLedgerMsCm(1413)).toBeCloseTo(1.413)
    expect(usCmToLedgerMsCm(0)).toBe(0)
  })

  it('should convert ledger mS/cm to µS/cm (read boundary)', () => {
    expect(ledgerMsCmToUsCm(2.0)).toBeCloseTo(2000)
    expect(ledgerMsCmToUsCm(1.413)).toBeCloseTo(1413)
  })

  it('should round-trip without scale drift', () => {
    const us = 12880
    expect(ledgerMsCmToUsCm(usCmToLedgerMsCm(us))).toBeCloseTo(us)
  })

  it('should map null/undefined through optional write helper', () => {
    expect(optionalUsCmToLedgerMsCm(null)).toBeNull()
    expect(optionalUsCmToLedgerMsCm(undefined)).toBeNull()
    expect(optionalUsCmToLedgerMsCm(1000)).toBeCloseTo(1.0)
  })
})
