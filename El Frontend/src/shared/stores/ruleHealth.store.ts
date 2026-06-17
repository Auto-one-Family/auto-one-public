/**
 * RuleHealth Store
 *
 * Holds the latest `rule.health` snapshot per rule_id, broadcast by the server
 * for critical climate rules (AUT-115).
 *
 * The store subscribes to the WebSocket once on first instantiation and
 * keeps an in-memory map of rule health payloads. Widgets read from this
 * store reactively (no direct REST calls in widgets).
 *
 * @see .claude/reference/api/WEBSOCKET_EVENTS.md
 */

import { defineStore } from 'pinia'
import { ref } from 'vue'
import { websocketService, type WebSocketMessage } from '@/services/websocket'
import type { MessageType } from '@/types'
import { createLogger } from '@/utils/logger'

const logger = createLogger('RuleHealthStore')

// =============================================================================
// Types
// =============================================================================

export interface RuleHealthDispatch {
  ts: string
  command: string
  state: string
  source: string
}

export interface RuleHealthSkip {
  ts: string
  reason: string
  consecutive_count: number
}

/**
 * Server-side payload contract for `rule.health` WebSocket events.
 *
 * Mirrors the Pydantic schema published by the server's rule health
 * broadcaster. All optional fields use `null` (not `undefined`) to match
 * the JSON contract.
 */
export interface RuleHealthPayload {
  rule_id: number
  rule_name: string
  is_critical: boolean
  setpoint: number | null
  current_value: number | null
  deviation: number | null
  target_esp_id: string | null
  target_esp_online: boolean
  target_esp_offline_since: string | null
  last_dispatch: RuleHealthDispatch | null
  last_skip: RuleHealthSkip | null
  degraded_since: string | null
  time_window_active: string | null
}

// =============================================================================
// Store
// =============================================================================

export const useRuleHealthStore = defineStore('ruleHealth', () => {
  // ---------------------------------------------------------------------------
  // State
  // ---------------------------------------------------------------------------

  /** Latest rule health snapshot per rule_id. */
  const ruleHealthMap = ref<Map<number, RuleHealthPayload>>(new Map())

  // ---------------------------------------------------------------------------
  // Actions
  // ---------------------------------------------------------------------------

  /**
   * Apply a `rule.health` payload to the in-memory map.
   * Replaces any existing snapshot for the same rule_id.
   */
  function handleRuleHealthEvent(payload: RuleHealthPayload): void {
    if (payload?.rule_id == null) {
      logger.warn('Ignoring rule.health event without rule_id', { payload })
      return
    }
    // Reassign Map to keep reactivity (Pinia tracks .value reassignment).
    const next = new Map(ruleHealthMap.value)
    next.set(payload.rule_id, payload)
    ruleHealthMap.value = next
  }

  /**
   * Read the latest snapshot for a given rule_id.
   * Returns `undefined` if no snapshot has been received yet.
   */
  function getRuleHealth(ruleId: number): RuleHealthPayload | undefined {
    return ruleHealthMap.value.get(ruleId)
  }

  // ---------------------------------------------------------------------------
  // WebSocket subscription (once per store lifetime)
  // ---------------------------------------------------------------------------

  // The 'rule.health' literal is part of MessageType (types/index.ts).
  // Cast keeps the WebSocketFilters typing stable while allowing dotted names.
  websocketService.subscribe(
    { types: ['rule.health' as MessageType] },
    (msg: WebSocketMessage) => {
      const payload = msg.data as unknown as RuleHealthPayload
      handleRuleHealthEvent(payload)
    },
  )

  return {
    // State
    ruleHealthMap,
    // Actions
    handleRuleHealthEvent,
    getRuleHealth,
  }
})
