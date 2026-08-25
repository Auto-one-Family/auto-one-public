import { describe, expect, it } from 'vitest'
import {
  formatAssistVolumeRatioLabel,
  volumeAltSourceLabel,
  ecWasserSourceLabel,
  buildSaltAssistOperatorHints,
  suggestionKindLabel,
} from '@/components/plants/saltCalculatorPreviewLabels'

describe('formatAssistVolumeRatioLabel (AUT-1368)', () => {
  it('should label equal server doses as equal volume share', () => {
    expect(formatAssistVolumeRatioLabel(667, 667)).toBe('gleicher Anteil')
  })

  it('should not hardcode EC 50:50 — uses server ml ratio', () => {
    expect(formatAssistVolumeRatioLabel(1000, 500)).toBe('Anteil A:B ≈ 2.0:1')
  })

  it('should fall back when doses are not positive', () => {
    expect(formatAssistVolumeRatioLabel(0, 100)).toBe('Anteil nach Volumen')
  })
})

describe('saltCalculator Klartext labels', () => {
  it('should map volume sources to operator language', () => {
    expect(volumeAltSourceLabel('v_real_anchor_flow')).toBe('gemessen')
    expect(volumeAltSourceLabel('ledger_prior_volume')).toBe('aus letzter Buchung')
    expect(volumeAltSourceLabel('manual_override')).toBe('von Hand eingegeben')
  })

  it('should map fresh-water EC sources without field names', () => {
    expect(ecWasserSourceLabel('tank_config')).toBe('am Tank hinterlegt')
    expect(ecWasserSourceLabel('none')).toBe('nicht hinterlegt')
  })

  it('should build operator hints without GPIO or dose_role jargon', () => {
    const hints = buildSaltAssistOperatorHints({
      volume_alt_l: 20,
      volume_alt_source: 'v_real_anchor_flow',
      volume_zugabe_l: 0,
      ec_wasser_us_cm: null,
      ec_wasser_source: 'none',
      ec_after_dilution_us_cm: 1500,
    })
    expect(hints).toHaveLength(1)
    expect(hints[0]).toMatch(/Tankvolumen 20 L \(gemessen\)/)
    expect(hints.join(' ')).not.toMatch(/GPIO|dose_role|V_real|SSOT|actuator/i)
  })

  it('should mention fresh water only when zugabe > 0', () => {
    const hints = buildSaltAssistOperatorHints({
      volume_alt_l: 18,
      volume_alt_source: 'v_real_minus_measured_zugabe',
      volume_zugabe_l: 2,
      ec_wasser_us_cm: 400,
      ec_wasser_source: 'tank_config',
      ec_after_dilution_us_cm: 1400,
    })
    expect(hints).toHaveLength(2)
    expect(hints[1]).toMatch(/2 L Frischwasser/)
    expect(hints[1]).toMatch(/400 µS\/cm/)
    expect(hints[1]).toMatch(/am Tank hinterlegt/)
  })

  it('should map suggestion_kind to direction labels (AUT-1404)', () => {
    expect(suggestionKindLabel('dose_up')).toBe('Aufdosieren')
    expect(suggestionKindLabel('dilute')).toBe('Verdünnen')
    expect(suggestionKindLabel('within_tolerance')).toBe('Im Zielband')
    expect(suggestionKindLabel('unavailable')).toBe('Kein Vorschlag')
  })
})
