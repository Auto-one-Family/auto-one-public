/**
 * Logic API Client
 *
 * Handles Cross-ESP automation rules.
 * Server endpoints: /v1/logic/rules, /v1/logic/execution_history
 *
 * @see El Servador/god_kaiser_server/src/api/v1/logic.py
 */

import api from "./index";
import type {
  LogicRule,
  LogicRulesResponse,
  ExecutionHistoryResponse,
  EscalationPolicy,
  PlanDomain,
  PlanMeasure,
  RuleGroup,
} from "@/types/logic";

// =============================================================================
// Request/Response Types
// =============================================================================

export interface LogicRuleCreate {
  name: string;
  description?: string;
  enabled?: boolean;
  conditions: unknown[];
  logic_operator?: "AND" | "OR";
  actions: unknown[];
  priority?: number;
  cooldown_seconds?: number;
  /** AUT-1115: Wait for settle_seconds after the last execution of this other rule before evaluating. */
  settle_after_rule_id?: string | null;
  /** AUT-1115: Settle window in seconds, evaluated against settle_after_rule_id's last execution. */
  settle_seconds?: number | null;
  /** AO-4 (AUT-993): Max total dose ml per rolling 24h across all executions (undefined = unlimited). */
  max_dose_ml_per_day?: number;
  max_executions_per_hour?: number;
  /** AUT-993 (B8): Max executions per rolling 24h window (undefined or 0 = unlimited). */
  max_executions_per_day?: number;
  is_critical?: boolean;
  escalation_policy?: EscalationPolicy | null;
  /** AUT-1113: Free-form rule metadata (e.g. AUT-1112 chemistry dose_config, AUT-1116 paired_rule_id). */
  rule_metadata?: Record<string, unknown>;
  /** AUT-1145/AUT-1283: Explicit display-group override. None/omitted = auto-derived server-side
   * (LogicService.derive_rule_group). One of RULE_GROUP_CATALOG when set. */
  rule_group?: RuleGroup | null;
  /** AUT-1232/AUT-1243: Opt-in plan subscription flag (default false). */
  follows_plan?: boolean;
  /** AUT-1232: Zone for plan subscription. */
  plan_zone_id?: string | null;
  /** AUT-1232: Optional subzone_config for plan subscription. */
  plan_subzone_config_id?: string | null;
  /** AUT-1232: Plan domain. */
  plan_domain?: PlanDomain | null;
  /** AUT-1232: Plan measure. */
  plan_measure?: PlanMeasure | null;
}

export interface LogicRuleUpdate {
  name?: string;
  description?: string;
  enabled?: boolean;
  conditions?: unknown[];
  logic_operator?: "AND" | "OR";
  actions?: unknown[];
  priority?: number;
  cooldown_seconds?: number;
  /** AUT-1115: Wait for settle_seconds after the last execution of this other rule before evaluating. */
  settle_after_rule_id?: string | null;
  /** AUT-1115: Settle window in seconds, evaluated against settle_after_rule_id's last execution. */
  settle_seconds?: number | null;
  /** AO-4 (AUT-993): Max total dose ml per rolling 24h across all executions (undefined = unlimited). */
  max_dose_ml_per_day?: number;
  /** AUT-1283: null explicitly clears the limit (server ge=1 — 0 is NOT persistable, never send 0). */
  max_executions_per_hour?: number | null;
  /** AUT-993 (B8): Max executions per rolling 24h window (undefined or 0 = unlimited). */
  max_executions_per_day?: number;
  is_critical?: boolean;
  escalation_policy?: EscalationPolicy | null;
  /** AUT-1113: Free-form rule metadata (e.g. AUT-1112 chemistry dose_config, AUT-1116 paired_rule_id). None = leave unchanged. */
  rule_metadata?: Record<string, unknown>;
  /** AUT-1145/AUT-1283: Explicit display-group override. Omit to leave unchanged; send null
   * explicitly to clear the override and revert to auto-derivation. One of RULE_GROUP_CATALOG. */
  rule_group?: RuleGroup | null;
  /** AUT-1232/AUT-1243: Opt-in plan subscription flag. */
  follows_plan?: boolean;
  /** AUT-1232: Zone for plan subscription. */
  plan_zone_id?: string | null;
  /** AUT-1232: Optional subzone_config for plan subscription. */
  plan_subzone_config_id?: string | null;
  /** AUT-1232: Plan domain. */
  plan_domain?: PlanDomain | null;
  /** AUT-1232: Plan measure. */
  plan_measure?: PlanMeasure | null;
}

/**
 * AUT-1145 (S0) bulk quick-field update request for the group-card Schnellfeld.
 * Exactly the three field groups from AUT-1148: active (An/Aus), threshold_value /
 * hysteresis_on_value+hysteresis_off_value (Schwellwert/Zielwert), and the
 * time-window fields (Zeiten). priority and cooldown_seconds are DELIBERATELY
 * absent — editor-only, see server schema RuleBulkQuickUpdateRequest.
 */
export interface RuleBulkQuickUpdateRequest {
  ids: string[];
  active?: boolean;
  threshold_value?: number;
  hysteresis_on_value?: number;
  hysteresis_off_value?: number;
  start_hour?: number;
  start_minute?: number;
  end_hour?: number;
  end_minute?: number;
  days_of_week?: number[];
}

export interface RuleBulkQuickUpdateResult {
  rule_id: string;
  success: boolean;
  error?: string;
}

export interface RuleBulkQuickUpdateResponse {
  success: boolean;
  message?: string;
  results: RuleBulkQuickUpdateResult[];
}

export interface ToggleResponse {
  success: boolean;
  message: string;
  rule_id: string;
  rule_name: string;
  enabled: boolean;
  previous_state: boolean;
}

export interface TestResponse {
  success: boolean;
  rule_id: string;
  rule_name: string;
  would_trigger: boolean;
  condition_results: {
    condition_index: number;
    condition_type: string;
    result: boolean;
    details: string;
    actual_value: number | null;
  }[];
  action_results: {
    action_index: number;
    action_type: string;
    would_execute: boolean;
    details: string;
    dry_run: boolean;
  }[];
  dry_run: boolean;
}

// =============================================================================
// Logic API
// =============================================================================

export const logicApi = {
  /**
   * Get all logic rules
   */
  async getRules(params?: {
    enabled?: boolean;
    page?: number;
    page_size?: number;
  }): Promise<LogicRulesResponse> {
    const response = await api.get<LogicRulesResponse>("/logic/rules", { params });
    return response.data;
  },

  /**
   * Get a specific logic rule by ID
   */
  async getRule(ruleId: string): Promise<LogicRule> {
    const response = await api.get<LogicRule>(`/logic/rules/${ruleId}`);
    return response.data;
  },

  /**
   * Create a new logic rule
   */
  async createRule(rule: LogicRuleCreate): Promise<LogicRule> {
    const response = await api.post<LogicRule>("/logic/rules", rule);
    return response.data;
  },

  /**
   * Update an existing logic rule
   */
  async updateRule(ruleId: string, update: LogicRuleUpdate): Promise<LogicRule> {
    const response = await api.put<LogicRule>(`/logic/rules/${ruleId}`, update);
    return response.data;
  },

  /**
   * Delete a logic rule
   */
  async deleteRule(ruleId: string): Promise<void> {
    await api.delete(`/logic/rules/${ruleId}`);
  },

  /**
   * AUT-1145 (S0): Bulk quick-field update for marked rules (Gruppenkarten-Schnellfeld).
   * Thin caller of the server's single bulk endpoint — the ONLY save path for the
   * group-card quick-field (AUT-1148 Fix-Philosophie: kein zweiter Save-Aufruf).
   */
  async bulkQuickUpdateRules(
    request: RuleBulkQuickUpdateRequest,
  ): Promise<RuleBulkQuickUpdateResponse> {
    const response = await api.post<RuleBulkQuickUpdateResponse>(
      "/logic/rules/bulk-quick-update",
      request,
    );
    return response.data;
  },

  /**
   * Toggle rule enabled/disabled
   */
  async toggleRule(ruleId: string, enabled: boolean, reason?: string): Promise<ToggleResponse> {
    const response = await api.post<ToggleResponse>(`/logic/rules/${ruleId}/toggle`, {
      enabled,
      reason,
    });
    return response.data;
  },

  /**
   * Test rule evaluation without executing actions
   */
  async testRule(
    ruleId: string,
    mockSensorValues?: Record<string, number>,
    mockTime?: string,
    dryRun = true,
  ): Promise<TestResponse> {
    const response = await api.post<TestResponse>(`/logic/rules/${ruleId}/test`, {
      mock_sensor_values: mockSensorValues,
      mock_time: mockTime,
      dry_run: dryRun,
    });
    return response.data;
  },

  /**
   * Get all currently degraded rules (AUT-111)
   */
  async getDegradedRules(): Promise<{ success: boolean; data: LogicRule[] }> {
    const response = await api.get<{ success: boolean; data: LogicRule[] }>("/logic/degraded");
    return response.data;
  },

  /**
   * Get execution history
   */
  async getExecutionHistory(params?: {
    rule_id?: string;
    success?: boolean;
    start_time?: string;
    end_time?: string;
    limit?: number;
  }): Promise<ExecutionHistoryResponse> {
    const response = await api.get<ExecutionHistoryResponse>("/logic/execution_history", {
      params,
    });
    return response.data;
  },

  /**
   * List available rule templates
   */
  async listTemplates(): Promise<{
    success: boolean;
    templates: Array<{
      template_id: string;
      name: string;
      description: string;
      version: string;
      required_parameters: string[];
      optional_parameters: Record<
        string,
        {
          type: string;
          default: unknown;
          description: string;
        }
      >;
    }>;
    total_count: number;
  }> {
    const response = await api.get("/logic/templates");
    return response.data;
  },

  /**
   * Get template details and parameter schema
   */
  async getTemplate(templateId: string): Promise<{
    success: boolean;
    template: {
      template_id: string;
      name: string;
      description: string;
      version: string;
      required_parameters: string[];
      optional_parameters: Record<
        string,
        {
          type: string;
          default: unknown;
          description: string;
        }
      >;
    };
  }> {
    const response = await api.get(`/logic/templates/${templateId}`);
    return response.data;
  },

  /**
   * Create rule from template with parameters
   */
  async instantiateTemplate(
    templateId: string,
    ruleName: string,
    parameters: Record<string, unknown>,
    description?: string,
  ): Promise<LogicRule> {
    const response = await api.post<LogicRule>(`/logic/templates/${templateId}/instantiate`, {
      rule_name: ruleName,
      description,
      parameters,
      enabled: true,
    });
    return response.data;
  },
};
