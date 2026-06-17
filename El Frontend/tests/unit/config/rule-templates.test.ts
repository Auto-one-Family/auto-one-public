/**
 * Tests for rule template configuration.
 * Verifies template structure, categories, and rule data validity.
 */

import { describe, it, expect } from 'vitest'
import { ruleTemplates, RULE_TEMPLATE_CATEGORIES } from '@/config/rule-templates'
import type { RuleTemplate } from '@/config/rule-templates'

describe('rule-templates', () => {
  it('exports at least 4 templates', () => {
    expect(ruleTemplates.length).toBeGreaterThanOrEqual(4)
  })

  it('all templates have unique ids', () => {
    const ids = ruleTemplates.map(t => t.id)
    expect(new Set(ids).size).toBe(ids.length)
  })

  it('all templates have required fields', () => {
    for (const tmpl of ruleTemplates) {
      expect(tmpl.id, `template should have id`).toBeTruthy()
      expect(tmpl.name, `${tmpl.id} should have name`).toBeTruthy()
      expect(tmpl.description, `${tmpl.id} should have description`).toBeTruthy()
      expect(tmpl.icon, `${tmpl.id} should have icon`).toBeDefined()
      expect(tmpl.category, `${tmpl.id} should have category`).toBeTruthy()
    }
  })

  it('all template categories are defined in RULE_TEMPLATE_CATEGORIES', () => {
    for (const tmpl of ruleTemplates) {
      expect(
        RULE_TEMPLATE_CATEGORIES[tmpl.category],
        `Category '${tmpl.category}' for template '${tmpl.id}' should be defined`
      ).toBeDefined()
    }
  })

  it('all categories have label and color', () => {
    for (const [key, cat] of Object.entries(RULE_TEMPLATE_CATEGORIES)) {
      expect(cat.label, `${key} should have label`).toBeTruthy()
      expect(cat.color, `${key} should have color`).toBeTruthy()
    }
  })

  it('all templates have valid rule data', () => {
    for (const tmpl of ruleTemplates) {
      const rule = tmpl.rule
      expect(rule.name, `${tmpl.id} rule should have name`).toBeTruthy()
      expect(rule.conditions, `${tmpl.id} rule should have conditions`).toBeDefined()
      expect(rule.conditions.length).toBeGreaterThanOrEqual(1)
      expect(rule.actions, `${tmpl.id} rule should have actions`).toBeDefined()
      expect(rule.actions.length).toBeGreaterThanOrEqual(1)
      expect(rule.logic_operator, `${tmpl.id} rule should have logic_operator`).toBeTruthy()
      expect(typeof rule.enabled).toBe('boolean')
    }
  })

  it('temp-alarm template targets DS18B20 sensor', () => {
    const tempAlarm = ruleTemplates.find(t => t.id === 'temp-alarm')
    expect(tempAlarm).toBeDefined()
    expect(tempAlarm!.category).toBe('climate')
    const sensorCond = tempAlarm!.rule.conditions.find(
      (c: any) => c.type === 'sensor' && c.sensor_type === 'DS18B20'
    )
    expect(sensorCond).toBeDefined()
  })

  it('irrigation template has time_window condition', () => {
    const irrigation = ruleTemplates.find(t => t.id === 'irrigation-schedule')
    expect(irrigation).toBeDefined()
    const timeCond = irrigation!.rule.conditions.find(
      (c: any) => c.type === 'time_window'
    )
    expect(timeCond).toBeDefined()
  })

  it('emergency-stop has highest priority', () => {
    const emergency = ruleTemplates.find(t => t.id === 'emergency-stop')
    expect(emergency).toBeDefined()
    const maxPriority = Math.max(...ruleTemplates.map(t => t.rule.priority ?? 0))
    expect(emergency!.rule.priority).toBe(maxPriority)
  })

  it('night-mode template uses schedule category', () => {
    const nightMode = ruleTemplates.find(t => t.id === 'night-mode')
    expect(nightMode).toBeDefined()
    expect(nightMode!.category).toBe('schedule')
  })
})
