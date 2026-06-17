/**
 * Rule Templates
 *
 * Pre-configured automation rule templates shown in the LogicView empty state.
 * Each template provides a LogicRule skeleton that users can customize.
 */

import {
  Thermometer,
  Droplets,
  Fan,
  Moon,
  FlaskConical,
  ShieldAlert,
} from 'lucide-vue-next'
import type { Component } from 'vue'
import type { LogicRule } from '@/types/logic'

export interface RuleTemplate {
  /** Unique template ID */
  id: string
  /** Display name */
  name: string
  /** Short description */
  description: string
  /** Lucide icon component */
  icon: Component
  /** Template category */
  category: 'climate' | 'irrigation' | 'safety' | 'schedule'
  /** Pre-filled rule data (without id, timestamps, etc.) */
  rule: Omit<LogicRule, 'id' | 'created_at' | 'updated_at' | 'last_triggered'>
}

export const RULE_TEMPLATE_CATEGORIES: Record<string, { label: string; color: string }> = {
  climate: { label: 'Klima', color: '#3b82f6' },
  irrigation: { label: 'Bewässerung', color: '#22c55e' },
  safety: { label: 'Sicherheit', color: '#ef4444' },
  schedule: { label: 'Zeitplan', color: '#8b5cf6' },
}

export const ruleTemplates: RuleTemplate[] = [
  {
    id: 'temp-alarm',
    name: 'Temperatur-Alarm',
    description: 'Beispiel: Wenn Temperatur über 30 °C → Lüfter AN. Schwellwert nach dem Verwenden anpassen.',
    icon: Thermometer,
    category: 'climate',
    rule: {
      name: 'Temperatur-Alarm',
      description: 'Automatische Lüftung bei Überhitzung',
      enabled: true,
      conditions: [{
        type: 'sensor',
        esp_id: '',
        gpio: 0,
        sensor_type: 'DS18B20',
        operator: '>',
        value: 30,
      }],
      logic_operator: 'AND',
      actions: [{
        type: 'actuator',
        esp_id: '',
        gpio: 0,
        command: 'ON',
      }],
      priority: 5,
      cooldown_seconds: 300,
    },
  },
  {
    id: 'irrigation-schedule',
    name: 'Bewässerungs-Zeitplan',
    description: 'Bewässert täglich zur eingestellten Zeit, aber nur wenn Bodenfeuchte unter 40 %. Werte nach dem Verwenden anpassen.',
    icon: Droplets,
    category: 'irrigation',
    rule: {
      name: 'Bewässerungs-Zeitplan',
      description: 'Tägliche Bewässerung morgens wenn Boden zu trocken',
      enabled: true,
      conditions: [
        {
          type: 'time_window',
          start_hour: 6,
          end_hour: 8,
          days_of_week: [1, 2, 3, 4, 5, 6, 0],
        },
        {
          type: 'sensor',
          esp_id: '',
          gpio: 0,
          sensor_type: 'soil_moisture',
          operator: '<',
          value: 40,
        },
      ],
      logic_operator: 'AND',
      actions: [{
        type: 'actuator',
        esp_id: '',
        gpio: 0,
        command: 'ON',
        duration: 600,
      }],
      priority: 3,
    },
  },
  {
    id: 'humidity-control',
    name: 'Luftfeuchte-Regelung',
    description: 'Beispiel: Wenn Luftfeuchte über 80 %RH → Lüfter AN. Schwellwert nach dem Verwenden anpassen.',
    icon: Fan,
    category: 'climate',
    rule: {
      name: 'Luftfeuchte-Regelung',
      description: 'Belüftung bei über 80% Luftfeuchtigkeit',
      enabled: true,
      conditions: [{
        type: 'sensor',
        esp_id: '',
        gpio: 0,
        sensor_type: 'SHT31',
        operator: '>',
        value: 80,
      }],
      logic_operator: 'AND',
      actions: [{
        type: 'actuator',
        esp_id: '',
        gpio: 0,
        command: 'ON',
      }],
      priority: 4,
      cooldown_seconds: 600,
    },
  },
  {
    id: 'night-mode',
    name: 'Nacht-Modus',
    description: 'Beispiel: Beleuchtung und Pumpen AUS zwischen 22:00 und 06:00. Zeiten nach dem Verwenden anpassen.',
    icon: Moon,
    category: 'schedule',
    rule: {
      name: 'Nacht-Modus',
      description: 'Beleuchtung und Pumpen aus in der Nacht',
      enabled: true,
      conditions: [{
        type: 'time_window',
        start_hour: 22,
        end_hour: 6,
      }],
      logic_operator: 'AND',
      actions: [{
        type: 'actuator',
        esp_id: '',
        gpio: 0,
        command: 'OFF',
      }],
      priority: 2,
    },
  },
  {
    id: 'ph-alarm',
    name: 'pH-Alarm',
    description: 'Beispiel: Benachrichtigung wenn pH-Wert über 6,5 steigt (kritisch für Pflanzen). Werte nach dem Verwenden anpassen.',
    icon: FlaskConical,
    category: 'safety',
    rule: {
      name: 'pH-Alarm',
      description: 'Benachrichtigung bei pH außerhalb 5.5-6.5',
      enabled: true,
      conditions: [{
        type: 'sensor',
        esp_id: '',
        gpio: 0,
        sensor_type: 'pH',
        operator: '>',
        value: 6.5,
      }],
      logic_operator: 'OR',
      actions: [{
        type: 'notification',
        channel: 'websocket',
        target: 'dashboard',
        message_template: 'pH-Wert kritisch: {{value}}',
      }],
      priority: 8,
      cooldown_seconds: 1800,
    },
  },
  {
    id: 'emergency-stop',
    name: 'Notfall-Abschaltung',
    description: 'Beispiel: Alle Aktoren sofort AUS wenn Temperatur über 45 °C — Sicherheitsabschaltung. Schwellwert nach dem Verwenden anpassen.',
    icon: ShieldAlert,
    category: 'safety',
    rule: {
      name: 'Notfall-Abschaltung',
      description: 'Sicherheitsabschaltung bei Temperatur über 45°C',
      enabled: true,
      conditions: [{
        type: 'sensor',
        esp_id: '',
        gpio: 0,
        sensor_type: 'DS18B20',
        operator: '>',
        value: 45,
      }],
      logic_operator: 'AND',
      actions: [{
        type: 'actuator',
        esp_id: '',
        gpio: 0,
        command: 'OFF',
      }],
      priority: 10,
      max_executions_per_hour: 5,
    },
  },
]
