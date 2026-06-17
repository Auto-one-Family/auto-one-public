/**
 * Logic API Client
 *
 * Handles Cross-ESP automation rules.
 * Server endpoints: /v1/logic/rules, /v1/logic/execution_history
 *
 * @see El Servador/god_kaiser_server/src/api/v1/logic.py
 */

import api from "./index";
import type { LogicRule, LogicRulesResponse, ExecutionHistoryResponse, EscalationPolicy } from "@/types/logic";

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
  max_executions_per_hour?: number;
  is_critical?: boolean;
  escalation_policy?: EscalationPolicy | null;
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
  max_executions_per_hour?: number;
  is_critical?: boolean;
  escalation_policy?: EscalationPolicy | null;
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
