/**
 * AUT-1304: paired_rule_id mapping in rule_metadata (LogicView roundtrip helpers).
 */

import { describe, it, expect } from 'vitest'
import {
  applyPairedRuleIdToMetadata,
  getPairedRuleIdFromMetadata,
} from '@/utils/logicRuleMetadata'

describe('logicRuleMetadata (AUT-1304)', () => {
  describe('getPairedRuleIdFromMetadata', () => {
    it('returns paired_rule_id when set', () => {
      expect(getPairedRuleIdFromMetadata({ paired_rule_id: 'rule-002' })).toBe('rule-002')
    })

    it('returns empty string when paired_rule_id is absent', () => {
      expect(getPairedRuleIdFromMetadata({ dose_config: { components: [] } })).toBe('')
      expect(getPairedRuleIdFromMetadata({})).toBe('')
    })
  })

  describe('applyPairedRuleIdToMetadata', () => {
    it('sets paired_rule_id without dropping other metadata keys', () => {
      const base = { dose_config: { components: [{ dose_ml: 1 }] } }
      expect(applyPairedRuleIdToMetadata(base, 'rule-pair')).toEqual({
        dose_config: { components: [{ dose_ml: 1 }] },
        paired_rule_id: 'rule-pair',
      })
    })

    it('removes paired_rule_id when cleared (empty select)', () => {
      const base = {
        paired_rule_id: 'rule-old',
        dose_config: { components: [] },
      }
      const cleared = applyPairedRuleIdToMetadata(base, '')
      expect(cleared).toEqual({ dose_config: { components: [] } })
      expect(cleared).not.toHaveProperty('paired_rule_id')
    })
  })
})
