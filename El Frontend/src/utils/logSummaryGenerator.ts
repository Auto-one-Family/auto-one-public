/**
 * Log Summary Generator
 *
 * Generates human-readable summaries for server log messages.
 * The original message is NEVER altered - summaries are ADDITIONAL context.
 */

import type { LogEntry } from '@/api/logs'

export interface LogSummary {
  icon: string
  title: string
  description?: string
  category: LogCategory
}

export type LogCategory =
  | 'scheduler'
  | 'sensor'
  | 'heartbeat'
  | 'mqtt'
  | 'config'
  | 'maintenance'
  | 'websocket'
  | 'actuator'
  | 'auth'
  | 'error'
  | 'system'

const CATEGORY_LABELS: Record<LogCategory, string> = {
  scheduler: 'Scheduler',
  sensor: 'Sensor',
  heartbeat: 'Heartbeat',
  mqtt: 'MQTT',
  config: 'Konfiguration',
  maintenance: 'Wartung',
  websocket: 'WebSocket',
  actuator: 'Aktor',
  auth: 'Authentifizierung',
  error: 'Fehler',
  system: 'System',
}

interface SummaryPattern {
  pattern: RegExp
  summary: (match: RegExpMatchArray, log: LogEntry) => LogSummary
}

const SUMMARY_PATTERNS: SummaryPattern[] = [
  // === Scheduler Jobs ===
  {
    pattern: /Running job "([^"]+)".*?\(scheduled at/,
    summary: (match) => ({
      icon: '\u25B6\uFE0F',
      title: 'Job wird ausgefuehrt',
      description: formatJobName(match[1]),
      category: 'scheduler',
    }),
  },
  {
    pattern: /Job "([^"]+)".*executed successfully/,
    summary: (match) => ({
      icon: '\u2705',
      title: 'Job erfolgreich ausgefuehrt',
      description: formatJobName(match[1]),
      category: 'scheduler',
    }),
  },
  {
    pattern: /Added job "([^"]+)".*trigger: interval\[([^\]]+)\]/,
    summary: (match) => ({
      icon: '\u23F0',
      title: 'Job registriert',
      description: `${formatJobName(match[1])} (alle ${match[2]})`,
      category: 'scheduler',
    }),
  },
  {
    pattern: /Removed job "([^"]+)"/,
    summary: (match) => ({
      icon: '\u23F9\uFE0F',
      title: 'Job entfernt',
      description: formatJobName(match[1]),
      category: 'scheduler',
    }),
  },
  {
    pattern: /Scheduler started/i,
    summary: () => ({
      icon: '\u{1F680}',
      title: 'Scheduler gestartet',
      category: 'scheduler',
    }),
  },

  // === Sensor Data ===
  {
    pattern: /Sensor data saved.*esp_id[=:]?\s*(\w+).*gpio[=:]?\s*(\d+)/i,
    summary: (match) => ({
      icon: '\u{1F4CA}',
      title: 'Sensordaten gespeichert',
      description: `ESP ${match[1]}, GPIO ${match[2]}`,
      category: 'sensor',
    }),
  },
  {
    pattern: /Sensor data received.*?(\w+).*?gpio[=:]?\s*(\d+)/i,
    summary: (match) => ({
      icon: '\u{1F4E1}',
      title: 'Sensordaten empfangen',
      description: `ESP ${match[1]}, GPIO ${match[2]}`,
      category: 'sensor',
    }),
  },
  {
    pattern: /Pi-enhanced processing.*?(\w+).*?gpio[=:]?\s*(\d+)/i,
    summary: (match) => ({
      icon: '\u{1F9EA}',
      title: 'Pi-Enhanced Verarbeitung',
      description: `ESP ${match[1]}, GPIO ${match[2]}`,
      category: 'sensor',
    }),
  },
  {
    pattern: /health_check_sensors:\s*(\d+)\s*sensor\(s\)\s*stale.*?healthy:\s*(\d+)/i,
    summary: (match) => ({
      icon: '\u26A0\uFE0F',
      title: 'Sensor-Gesundheitscheck',
      description: `${match[1]} inaktiv, ${match[2]} gesund`,
      category: 'maintenance',
    }),
  },
  {
    pattern: /Sensor stale:.*?ESP\s*(\w+).*?GPIO\s*(\d+).*?no data for (\d+)/i,
    summary: (match) => ({
      icon: '\u23F0',
      title: 'Sensor inaktiv',
      description: `${match[1]} GPIO ${match[2]} \u2013 keine Daten seit ${formatSeconds(parseInt(match[3]))}`,
      category: 'sensor',
    }),
  },

  // === Heartbeat ===
  {
    pattern: /\[AUTO-HB\]\s*(\w+)\s*heartbeat published.*?state=(\w+)/i,
    summary: (match) => ({
      icon: '\u{1F493}',
      title: 'Heartbeat gesendet',
      description: `${match[1]} ist ${match[2] === 'OPERATIONAL' ? 'online' : match[2].toLowerCase()}`,
      category: 'heartbeat',
    }),
  },
  {
    pattern: /Heartbeat.*?(\w+).*?(?:online|connected)/i,
    summary: (match) => ({
      icon: '\u{1F493}',
      title: 'Heartbeat empfangen',
      description: match[1],
      category: 'heartbeat',
    }),
  },
  {
    pattern: /Device\s+(\w+)\s+timed?\s*out/i,
    summary: (match) => ({
      icon: '\u{1F4A4}',
      title: 'Geraet nicht erreichbar',
      description: `${match[1]} hat nicht rechtzeitig geantwortet`,
      category: 'heartbeat',
    }),
  },

  // === MQTT ===
  {
    pattern: /MQTT (connected|broker connected)/i,
    summary: () => ({
      icon: '\u{1F50C}',
      title: 'MQTT verbunden',
      description: 'Broker-Verbindung hergestellt',
      category: 'mqtt',
    }),
  },
  {
    pattern: /MQTT.*disconnect|broker unavailable/i,
    summary: () => ({
      icon: '\u26A0\uFE0F',
      title: 'MQTT getrennt',
      description: 'Broker-Verbindung verloren',
      category: 'mqtt',
    }),
  },
  {
    pattern: /Registered (\d+) MQTT handlers/i,
    summary: (match) => ({
      icon: '\u2705',
      title: 'MQTT Handler registriert',
      description: `${match[1]} Handler aktiv`,
      category: 'mqtt',
    }),
  },
  {
    pattern: /Subscribed to:\s*(.+)/i,
    summary: (match) => ({
      icon: '\u{1F4E9}',
      title: 'MQTT Subscription',
      description: match[1].length > 60 ? match[1].slice(0, 57) + '...' : match[1],
      category: 'mqtt',
    }),
  },
  {
    pattern: /Handler returned False/i,
    summary: () => ({
      icon: '\u26A0\uFE0F',
      title: 'MQTT Handler Fehler',
      description: 'Ein Handler konnte die Nachricht nicht verarbeiten',
      category: 'mqtt',
    }),
  },

  // === WebSocket ===
  {
    pattern: /WebSocket client connected.*?client[_\s]*(\w+)/i,
    summary: (match) => ({
      icon: '\u{1F50C}',
      title: 'WebSocket verbunden',
      description: `Client ${match[1].slice(0, 8)}...`,
      category: 'websocket',
    }),
  },
  {
    pattern: /WebSocket client disconnected.*?client[_\s]*(\w+)/i,
    summary: (match) => ({
      icon: '\u274C',
      title: 'WebSocket getrennt',
      description: `Client ${match[1].slice(0, 8)}...`,
      category: 'websocket',
    }),
  },
  {
    pattern: /WebSocket.*?broadcast.*?(\d+)\s*client/i,
    summary: (match) => ({
      icon: '\u{1F4E2}',
      title: 'WebSocket Broadcast',
      description: `An ${match[1]} Client(s)`,
      category: 'websocket',
    }),
  },

  // === Config ===
  {
    pattern: /Rejected GPIO config.*Only (DC|ONEWIRE|I2C|PWM)/i,
    summary: (match) => ({
      icon: '\u274C',
      title: 'GPIO-Konfiguration abgelehnt',
      description: `Pin-Typ-Konflikt (${match[1]} erwartet)`,
      category: 'config',
    }),
  },
  {
    pattern: /Unknown board_module.*?defaulting to (\w+)/i,
    summary: (match) => ({
      icon: '\u2699\uFE0F',
      title: 'Unbekanntes Board-Modul',
      description: `Fallback auf ${match[1]}`,
      category: 'config',
    }),
  },
  {
    pattern: /Config.*sent to\s*(\w+)/i,
    summary: (match) => ({
      icon: '\u{1F4E4}',
      title: 'Konfiguration gesendet',
      description: `An ${match[1]}`,
      category: 'config',
    }),
  },

  // === Actuator ===
  {
    pattern: /Actuator command.*?esp[_\s]*(\w+).*?gpio[=:]?\s*(\d+)/i,
    summary: (match) => ({
      icon: '\u{1F527}',
      title: 'Aktor-Befehl',
      description: `ESP ${match[1]}, GPIO ${match[2]}`,
      category: 'actuator',
    }),
  },
  {
    pattern: /Emergency.?stop.*?(activated|triggered|deactivated)/i,
    summary: (match) => ({
      icon: '\u{1F6A8}',
      title: match[1].toLowerCase().includes('deact') ? 'Notaus aufgehoben' : 'Notaus aktiviert',
      category: 'actuator',
    }),
  },

  // === Auth ===
  {
    pattern: /Login.*?successful.*?user[=:\s]*(\w+)/i,
    summary: (match) => ({
      icon: '\u{1F513}',
      title: 'Anmeldung erfolgreich',
      description: `Benutzer: ${match[1]}`,
      category: 'auth',
    }),
  },
  {
    pattern: /Login.*?failed|authentication.*?failed/i,
    summary: () => ({
      icon: '\u{1F512}',
      title: 'Anmeldung fehlgeschlagen',
      category: 'auth',
    }),
  },

  // === Maintenance ===
  {
    pattern: /Cleanup.*?deleted (\d+).*?freed ([\d.]+)/i,
    summary: (match) => ({
      icon: '\u{1F9F9}',
      title: 'Bereinigung abgeschlossen',
      description: `${match[1]} Eintraege entfernt, ${match[2]} MB freigegeben`,
      category: 'maintenance',
    }),
  },
  {
    pattern: /Maintenance.*?started|MaintenanceService.*?init/i,
    summary: () => ({
      icon: '\u{1F527}',
      title: 'Wartungsdienst gestartet',
      category: 'maintenance',
    }),
  },

  // === System ===
  {
    pattern: /Application startup complete/i,
    summary: () => ({
      icon: '\u{1F680}',
      title: 'Server gestartet',
      description: 'Anwendung erfolgreich initialisiert',
      category: 'system',
    }),
  },
  {
    pattern: /Shutting down|shutdown/i,
    summary: () => ({
      icon: '\u23FB\uFE0F',
      title: 'Server wird heruntergefahren',
      category: 'system',
    }),
  },
  {
    pattern: /Database.*?connected|DB.*?initialized/i,
    summary: () => ({
      icon: '\u{1F4BE}',
      title: 'Datenbank verbunden',
      category: 'system',
    }),
  },
]

export function generateSummary(log: LogEntry): LogSummary | null {
  for (const { pattern, summary } of SUMMARY_PATTERNS) {
    const match = log.message.match(pattern)
    if (match) {
      return summary(match, log)
    }
  }

  // Fallback for ERROR/CRITICAL levels
  if (log.level === 'CRITICAL') {
    return {
      icon: '\u{1F534}',
      title: 'Kritischer Fehler',
      description: truncate(log.message, 60),
      category: 'error',
    }
  }

  if (log.level === 'ERROR') {
    return {
      icon: '\u{1F534}',
      title: 'Fehler aufgetreten',
      description: truncate(log.message, 60),
      category: 'error',
    }
  }

  if (log.level === 'WARNING') {
    return {
      icon: '\u26A0\uFE0F',
      title: 'Warnung',
      description: truncate(log.message, 60),
      category: 'system',
    }
  }

  return null
}

export function formatCategoryLabel(category: LogCategory): string {
  return CATEGORY_LABELS[category] || category
}

// === Helpers ===

function formatJobName(name: string): string {
  return name
    .replace(/SimulationScheduler_/g, 'Simulation: ')
    .replace(/MaintenanceService_/g, 'Wartung: ')
    .replace(/_job$/g, '')
    .replace(/_/g, ' ')
}

function formatSeconds(s: number): string {
  if (s < 60) return `${s} Sekunden`
  if (s < 3600) return `${Math.floor(s / 60)} Minuten`
  return `${Math.floor(s / 3600)} Stunden`
}

function truncate(str: string, maxLen: number): string {
  if (str.length <= maxLen) return str
  return str.slice(0, maxLen - 3) + '...'
}
