import { describe, expect, it } from 'vitest'
import {
  computeDelta,
  findIstSensorValue,
  formatDelta,
  formatIstSollValue,
  measureKeyFromTarget,
  measureLabel,
  resolvedViaLabel,
  TANK_DETAIL_QUERY_KEY,
  TANK_DETAIL_ROUTE,
  tankDetailHref,
} from '@/components/plants/tankIstSollFormat'

describe('tankIstSollFormat', () => {
  // ===========================================================================
  // formatIstSollValue — the binding "never 0" rule
  // ===========================================================================
  describe('formatIstSollValue', () => {
    it('should render null as em-dash, never "0"', () => {
      expect(formatIstSollValue(null)).toBe('—')
    })

    it('should render undefined as em-dash', () => {
      expect(formatIstSollValue(undefined)).toBe('—')
    })

    it('should render NaN as em-dash', () => {
      expect(formatIstSollValue(Number.NaN)).toBe('—')
    })

    it('should format an actual 0 reading as "0,00", not em-dash', () => {
      expect(formatIstSollValue(0)).toBe('0,00')
    })

    it('should format a positive value with German decimal comma', () => {
      expect(formatIstSollValue(1.85)).toBe('1,85')
    })

    it('should respect a custom decimals argument', () => {
      expect(formatIstSollValue(6.123, 1)).toBe('6,1')
    })
  })

  // ===========================================================================
  // computeDelta — only when BOTH sides are numeric
  // ===========================================================================
  describe('computeDelta', () => {
    it('should return null when ist is missing', () => {
      expect(computeDelta(null, 1.8)).toBeNull()
      expect(computeDelta(undefined, 1.8)).toBeNull()
    })

    it('should return null when soll is missing', () => {
      expect(computeDelta(1.9, null)).toBeNull()
      expect(computeDelta(1.9, undefined)).toBeNull()
    })

    it('should return null when both are missing', () => {
      expect(computeDelta(null, null)).toBeNull()
    })

    it('should compute ist - soll when both are numeric', () => {
      expect(computeDelta(2.1, 1.8)).toBeCloseTo(0.3)
      expect(computeDelta(1.5, 1.8)).toBeCloseTo(-0.3)
    })

    it('should treat an actual 0 ist as numeric (not missing)', () => {
      expect(computeDelta(0, 1.8)).toBeCloseTo(-1.8)
    })
  })

  // ===========================================================================
  // formatDelta
  // ===========================================================================
  describe('formatDelta', () => {
    it('should render null delta as em-dash', () => {
      expect(formatDelta(null)).toBe('—')
    })

    it('should prefix positive deltas with +', () => {
      expect(formatDelta(0.3)).toBe('+0,30')
    })

    it('should keep the sign for negative deltas', () => {
      expect(formatDelta(-0.3)).toBe('-0,30')
    })

    it('should not prefix zero with +', () => {
      expect(formatDelta(0)).toBe('0,00')
    })
  })

  // ===========================================================================
  // findIstSensorValue
  // ===========================================================================
  describe('findIstSensorValue', () => {
    it('should return null when no devices are assigned', () => {
      expect(findIstSensorValue([{ device_id: 'ESP_1', sensors: [] }], [], 'ec')).toBeNull()
    })

    it('should return null when the assigned device has no matching sensor', () => {
      const devices = [
        { device_id: 'ESP_1', sensors: [{ sensor_type: 'temp', raw_value: 22 }] },
      ]
      expect(findIstSensorValue(devices, ['ESP_1'], 'ec')).toBeNull()
    })

    it('should prefer processed_value over raw_value', () => {
      const devices = [
        {
          device_id: 'ESP_1',
          sensors: [{ sensor_type: 'ec', raw_value: 1.1, processed_value: 1.9 }],
        },
      ]
      expect(findIstSensorValue(devices, ['ESP_1'], 'ec')).toBe(1.9)
    })

    it('should fall back to raw_value when processed_value is missing', () => {
      const devices = [
        { device_id: 'ESP_1', sensors: [{ sensor_type: 'ph', raw_value: 6.2 }] },
      ]
      expect(findIstSensorValue(devices, ['ESP_1'], 'ph')).toBe(6.2)
    })

    it('should match sensor_type case-insensitively', () => {
      const devices = [
        { device_id: 'ESP_1', sensors: [{ sensor_type: 'EC', raw_value: 1.4 }] },
      ]
      expect(findIstSensorValue(devices, ['ESP_1'], 'ec')).toBe(1.4)
    })

    it('should ignore devices not in the assigned list', () => {
      const devices = [
        { device_id: 'ESP_1', sensors: [{ sensor_type: 'ec', raw_value: 1.4 }] },
        { device_id: 'ESP_2', sensors: [{ sensor_type: 'ec', raw_value: 2.4 }] },
      ]
      expect(findIstSensorValue(devices, ['ESP_2'], 'ec')).toBe(2.4)
    })

    it('should fall back to esp_id when device_id is absent (Mock ESP)', () => {
      const devices = [
        { esp_id: 'ESP_MOCK_1', sensors: [{ sensor_type: 'ph', raw_value: 6.5 }] },
      ]
      expect(findIstSensorValue(devices, ['ESP_MOCK_1'], 'ph')).toBe(6.5)
    })

    it('should return null (not 0) when the matching sensor has no value yet', () => {
      const devices = [
        { device_id: 'ESP_1', sensors: [{ sensor_type: 'ec', raw_value: null }] },
      ]
      expect(findIstSensorValue(devices, ['ESP_1'], 'ec')).toBeNull()
    })

    it('should resolve Messbox temperature via sht31_temp or ds18b20 (AUT-1537)', () => {
      const sht = [
        { device_id: 'ESP_1', sensors: [{ sensor_type: 'sht31_temp', raw_value: 22.5 }] },
      ]
      expect(findIstSensorValue(sht, ['ESP_1'], 'temperature')).toBe(22.5)

      const ds = [
        { device_id: 'ESP_1', sensors: [{ sensor_type: 'ds18b20', processed_value: 19.1 }] },
      ]
      expect(findIstSensorValue(ds, ['ESP_1'], 'temperature')).toBe(19.1)
    })

    it('should not treat sht31_humidity as temperature', () => {
      const devices = [
        {
          device_id: 'ESP_1',
          sensors: [{ sensor_type: 'sht31_humidity', raw_value: 55 }],
        },
      ]
      expect(findIstSensorValue(devices, ['ESP_1'], 'temperature')).toBeNull()
    })
  })

  // ===========================================================================
  // Labels
  // ===========================================================================
  describe('measureKeyFromTarget / measureLabel / resolvedViaLabel', () => {
    it('should map target_ec/target_ph to ec/ph sensor keys', () => {
      expect(measureKeyFromTarget('target_ec')).toBe('ec')
      expect(measureKeyFromTarget('target_ph')).toBe('ph')
    })

    it('should label measures in German-friendly short form', () => {
      expect(measureLabel('target_ec')).toBe('EC')
      expect(measureLabel('target_ph')).toBe('pH')
    })

    it('should label resolution source', () => {
      expect(resolvedViaLabel('zone')).toBe('via Zone')
      expect(resolvedViaLabel('subzone')).toBe('via Subzone')
      expect(resolvedViaLabel('none')).toBe('kein Plan-Segment')
    })
  })

  describe('tankDetailHref (AUT-1327 / AUT-1339 NL-Tab)', () => {
    it('should point at the nutrient-solution detail route', () => {
      expect(TANK_DETAIL_ROUTE).toBe('/nutrient-solution')
      expect(TANK_DETAIL_QUERY_KEY).toBe('tank')
      expect(tankDetailHref('abc-123')).toBe('/nutrient-solution/abc-123')
      expect(tankDetailHref('id/with?special')).toBe(
        `/nutrient-solution/${encodeURIComponent('id/with?special')}`,
      )
    })
  })
})
